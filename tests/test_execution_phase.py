"""Execution policy and virtual-time acceptance tests, independent of QPU speed."""

from types import SimpleNamespace

import pytest
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.execution_info import BatchCounts, PreparedBatch
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.flow.execution.phase_execution import ConcreteExecutionPhase


class DeterministicPreparation:
    """Preserve the real batch layout contract, with one second per shot."""

    def __init__(self, fail_calls=(), duration=1.0):
        self.calls = []
        self.fail_calls = set(fail_calls)
        self.duration = duration

    def prepare_batch(self, machine, jobs, *, seed):
        self.calls.append((machine.name, tuple(jobs), seed))
        if len(self.calls) in self.fail_calls:
            raise RuntimeError("deliberate preparation failure")
        width = sum(job.circuit.num_qubits for job in jobs.values())
        bits = sum(job.circuit.num_clbits for job in jobs.values())
        merged = QuantumCircuit(width, bits)
        classical_bits = {}
        qoffset = coffset = 0
        for job_id, job in jobs.items():
            circuit = job.circuit
            classical_bits[job_id] = tuple(range(coffset, coffset + circuit.num_clbits))
            merged.compose(
                circuit,
                qubits=list(range(qoffset, qoffset + circuit.num_qubits)),
                clbits=list(classical_bits[job_id]),
                inplace=True,
            )
            qoffset += circuit.num_qubits
            coffset += circuit.num_clbits
        return PreparedBatch(
            job_ids=tuple(jobs), merged_circuit=merged, transpiled_circuit=merged,
            classical_bits=classical_bits, logical_qubits=width,
            duration_per_shot=(self.duration[machine.name]
                               if isinstance(self.duration, dict) else self.duration),
        )


class DeterministicExecution:
    def __init__(self, shot_limit=None, outcomes=None):
        self.calls = []
        self.shot_limit = shot_limit
        self.outcomes = outcomes or {}

    def max_shots(self, machine):
        return (self.shot_limit[machine.name]
                if isinstance(self.shot_limit, dict) else self.shot_limit)

    def execute_batch(self, machine, prepared, shots, *, seed):
        self.calls.append((machine.name, prepared.job_ids, shots, seed))
        outcome = self.outcomes.get(len(self.calls))
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is not None:
            return outcome
        key = "0" * prepared.merged_circuit.num_clbits
        return BatchCounts({key: shots}, {key: shots})


def make_machines(**capacities):
    return {
        name: MachineCharacteristic(
            name=name,
            quantum_machine=SimpleNamespace(num_qubits=capacity),
            capacity=capacity,
        )
        for name, capacity in capacities.items()
    }


def make_job(name, shots=1, *, width=2, arrival=0, machine="machine", order=0):
    circuit = QuantumCircuit(width, width)
    circuit.h(0)
    circuit.measure(range(width), range(width))
    return SchedulerJobInfo(
        job_information=JobInfo(
            job_name=name, circuit=circuit, num_qubits=width,
            shots=shots, arrival_time=arrival,
        ),
        assigned_machine=machine, dispatch_order=order, depends_on=[],
    )


def make_phase(*, fail_preparation=(), outcomes=None, shot_limit=None, duration=1.0):
    preparation = DeterministicPreparation(fail_preparation, duration=duration)
    execution = DeterministicExecution(shot_limit, outcomes)
    phase = ConcreteExecutionPhase(pre_execution=preparation, main_execution=execution)
    return phase, preparation, execution


def execute(phase, machines, jobs, **kwargs):
    return phase.execute(machines, jobs, gantt_output_path=None, **kwargs)


def batches(phase):
    return [(batch.job_ids, batch.shots) for batch in phase.execution_summary.batches]


def assert_success(result, shots):
    assert result.status == "SUCCEEDED"
    assert result.error_reason is None
    assert result.requested_shots == result.completed_shots == shots
    assert sum(result.distribution_no_noise.values()) == shots
    assert sum(result.distribution_with_noise.values()) == shots
    assert result.fidelity == pytest.approx(1)


def test_single_job_defaults_preserve_canonical_keys_and_input_objects():
    phase, preparation, main = make_phase()
    machines = make_machines(machine=4)
    machines["machine"].name = "different embedded machine name"
    scheduled = make_job("different embedded job name", shots=None, arrival=None)
    scheduled.job_information.num_qubits = None
    original_circuit = scheduled.job_information.circuit.copy()
    original_job = vars(scheduled.job_information).copy()
    original_schedule = vars(scheduled).copy()

    result = execute(phase, machines, {"canonical job": scheduled}, seed=37)

    assert list(result) == ["canonical job"]
    assert_success(result["canonical job"], 1024)
    assert result["canonical job"].job_info is scheduled.job_information
    assert result["canonical job"].assigned_machine == "machine"
    assert result["canonical job"].start_time == 0
    assert result["canonical job"].end_time == 1024
    assert result["canonical job"].execution_time == 1024
    assert scheduled.job_information.circuit == original_circuit
    assert vars(scheduled.job_information) == original_job
    assert vars(scheduled) == original_schedule
    assert preparation.calls[0][2] == 37
    assert main.calls[0][3] == 37


@pytest.mark.parametrize("policy", ["strict", "backfill"])
@pytest.mark.parametrize(
    ("predecessor", "expected_batches", "expected_start"),
    [
        ("A", [(('A', 'B'), 100), (('B', 'C'), 150), (('B',), 50)], 100),
        ("B", [(('A', 'B'), 100), (('B',), 200), (('C',), 150)], 300),
    ],
)
def test_dependent_job_waits_for_all_predecessor_shots(
    policy, predecessor, expected_batches, expected_start,
):
    phase, _, _ = make_phase()
    jobs = {name: make_job(name, shots, order=order)
            for order, (name, shots) in enumerate([("A", 100), ("B", 300), ("C", 150)])}
    jobs["C"].depends_on = [jobs[predecessor].job_information]

    result = execute(phase, make_machines(machine=4), jobs, queue_policy=policy)

    assert batches(phase) == expected_batches
    assert result["C"].start_time == expected_start
    for name, shots in [("A", 100), ("B", 300), ("C", 150)]:
        assert_success(result[name], shots)
    assert result["B"].end_time == 300


@pytest.mark.parametrize("policy", ["strict", "backfill"])
@pytest.mark.parametrize("obstacle", ["arrival", "dependency", "capacity"])
def test_queue_policy_controls_admission_past_an_ineligible_head(policy, obstacle):
    phase, _, _ = make_phase()
    machines = make_machines(machine=4, auxiliary=2)
    jobs = {
        "A": make_job("A", 10, width=3 if obstacle == "capacity" else 2),
        "B": make_job("B", 5, order=1, arrival=20 if obstacle == "arrival" else 0),
        "C": make_job("C", 5, width=1 if obstacle == "capacity" else 2, order=2),
    }
    if obstacle == "dependency":
        jobs["D"] = make_job("D", 20, machine="auxiliary")
        jobs["B"].depends_on = [jobs["D"].job_information]

    result = execute(phase, machines, jobs, queue_policy=policy)

    expected_start = 0 if policy == "backfill" else (10 if obstacle == "capacity" else 20)
    assert result["C"].start_time == expected_start
    assert result["B"].start_time == (10 if obstacle == "capacity" else 20)
    assert all(job.status == "SUCCEEDED" for job in result.values())
    assert all(batch.logical_qubits <= machines[batch.machine_name].capacity
               for batch in phase.execution_summary.batches)


def test_arrival_during_a_batch_waits_until_the_batch_boundary():
    phase, _, _ = make_phase()
    jobs = {"A": make_job("A", 10), "B": make_job("B", 2, arrival=3, order=1)}

    result = execute(phase, make_machines(machine=4), jobs)

    assert result["B"].start_time == 10
    assert batches(phase) == [(('A',), 10), (('B',), 2)]


def test_cross_machine_overlap_and_same_time_completions_unlock_dependencies():
    phase, _, _ = make_phase()
    machines = make_machines(first=2, second=2, third=2)
    jobs = {
        "A": make_job("A", 5, machine="first"),
        "B": make_job("B", 5, machine="second"),
        "C": make_job("C", 2, machine="first", order=1),
        "D": make_job("D", 1, machine="third", arrival=3),
    }
    jobs["C"].depends_on = [jobs["A"].job_information, jobs["B"].job_information]

    result = execute(phase, machines, jobs)

    assert (result["A"].start_time, result["B"].start_time) == (0, 0)
    assert (result["D"].start_time, result["D"].end_time) == (3, 4)
    assert (result["C"].start_time, result["C"].end_time) == (5, 7)
    assert phase.execution_summary.makespan == 7


@pytest.mark.parametrize("policy", ["strict", "backfill"])
def test_float_roundoff_does_not_delay_a_dependency_at_the_same_batch_boundary(policy):
    phase, _, _ = make_phase(
        duration={"first": 0.3, "second": 0.1},
        shot_limit={"first": None, "second": 2},
    )
    jobs = {
        "A": make_job("A", 4, machine="first"),
        "B": make_job("B", 1, machine="first", order=1),
        "C": make_job("C", 1, machine="first", order=2),
        "D": make_job("D", 3, machine="second"),
    }
    jobs["C"].depends_on = [jobs["D"].job_information]

    result = execute(phase, make_machines(first=4, second=2), jobs, queue_policy=policy)

    first_batches = [batch for batch in phase.execution_summary.batches
                     if batch.machine_name == "first"]
    assert [(batch.job_ids, batch.shots) for batch in first_batches] == [
        (('A', 'B'), 1), (('A', 'C'), 1), (('A',), 2),
    ]
    assert result["C"].start_time == result["D"].end_time
    assert result["C"].start_time == pytest.approx(0.3, rel=1e-15, abs=0)
    assert result["C"].start_time >= result["B"].end_time


def test_float_roundoff_arrival_joins_the_matching_batch_boundary_without_starting_early():
    phase, _, _ = make_phase(duration=0.3)
    arrival = 0.2 + 0.1
    jobs = {
        "A": make_job("A", 4),
        "B": make_job("B", 1, order=1),
        "C": make_job("C", 1, order=2, arrival=arrival),
    }

    result = execute(phase, make_machines(machine=4), jobs)

    assert batches(phase) == [(('A', 'B'), 1), (('A', 'C'), 1), (('A',), 2)]
    assert result["C"].start_time == arrival
    assert result["C"].start_time >= result["B"].end_time


@pytest.mark.parametrize(
    ("duration", "arrival"),
    [(0.3, 0.3 + 1e-12), (1e-15, 2e-15)],
    ids=["picosecond_difference", "femtosecond_durations"],
)
def test_distinct_small_time_intervals_are_not_coalesced(duration, arrival):
    phase, _, _ = make_phase(duration=duration)
    jobs = {
        "A": make_job("A", 4),
        "B": make_job("B", 1, order=1),
        "C": make_job("C", 1, order=2, arrival=arrival),
    }

    result = execute(phase, make_machines(machine=4), jobs)

    assert batches(phase) == [(('A', 'B'), 1), (('A',), 3), (('C',), 1)]
    assert result["C"].start_time >= arrival
    assert result["C"].start_time == pytest.approx(4 * duration, rel=1e-15, abs=0)


@pytest.mark.parametrize("policy", ["strict", "backfill"])
def test_ffd_group_barriers_wait_for_every_job_in_the_previous_group(policy):
    phase, _, _ = make_phase()
    machines = make_machines(machine=4)
    jobs = {name: make_job(name, shots)
            for name, shots in [("A", 100), ("B", 300), ("C", 150)]}
    FFD().execute(jobs, machines)

    result = execute(phase, machines, jobs, queue_policy=policy)

    assert len(jobs["C"].depends_on) == 2
    assert result["C"].start_time == 300
    assert batches(phase) == [(('A', 'B'), 100), (('B',), 200), (('C',), 150)]


def test_backend_shot_limit_creates_exact_partial_batches():
    phase, _, main = make_phase(shot_limit=64)

    result = execute(phase, make_machines(machine=2), {"A": make_job("A", 150)})

    assert [call[2] for call in main.calls] == [64, 64, 22]
    assert batches(phase) == [(('A',), 64), (('A',), 64), (('A',), 22)]
    assert_success(result["A"], 150)
    assert result["A"].end_time == 150


def test_dispatch_order_takes_precedence_over_dictionary_insertion_order():
    phase, _, _ = make_phase()
    jobs = {name: make_job(name, order=order)
            for name, order in [("C", 2), ("B", 1), ("A", 0)]}

    result = execute(phase, make_machines(machine=2), jobs)

    assert batches(phase) == [(('A',), 1), (('B',), 1), (('C',), 1)]
    assert [result[name].start_time for name in "ABC"] == [0, 1, 2]


def test_virtual_duration_multiplies_seconds_per_shot_and_excludes_arrival_idle_time():
    phase, _, _ = make_phase(duration=0.25)

    result = execute(phase, make_machines(machine=2), {"A": make_job("A", 4, arrival=2)})

    assert result["A"].start_time == 2
    assert result["A"].end_time == 3
    assert result["A"].execution_time == 1
    assert phase.execution_summary.makespan == 3
    assert phase.execution_summary.machines["machine"].utilization == pytest.approx(1 / 3)


def test_low_fidelity_does_not_add_shots_or_trigger_a_retry():
    phase, _, main = make_phase(outcomes={1: BatchCounts({"00": 7}, {"11": 7})})

    result = execute(phase, make_machines(machine=2), {"A": make_job("A", 7)})

    assert result["A"].status == "SUCCEEDED"
    assert result["A"].completed_shots == 7
    assert result["A"].fidelity == 0
    assert result["A"].distribution_no_noise == {"00": 7}
    assert result["A"].distribution_with_noise == {"11": 7}
    assert len(main.calls) == 1


def test_accumulation_uses_each_new_batch_classical_mapping():
    phase, preparation, _ = make_phase(outcomes={
        1: BatchCounts({"1001": 2}, {"1001": 2}),
        2: BatchCounts({"0110": 3}, {"0110": 3}),
        3: BatchCounts({"10": 1}, {"10": 1}),
    })
    jobs = {name: make_job(name, shots, order=order)
            for order, (name, shots) in enumerate([("A", 2), ("B", 6), ("C", 3)])}
    jobs["C"].depends_on = [jobs["A"].job_information]

    result = execute(phase, make_machines(machine=4), jobs)

    assert batches(phase) == [(('A', 'B'), 2), (('B', 'C'), 3), (('B',), 1)]
    assert [call[1] for call in preparation.calls] == [('A', 'B'), ('B', 'C'), ('B',)]
    for name, expected in [("A", {"01": 2}), ("B", {"10": 6}), ("C", {"01": 3})]:
        assert result[name].distribution_no_noise == expected
        assert result[name].distribution_with_noise == expected


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("deliberate backend failure"),
        BatchCounts({"00": 2}, {"00": 3}),
        BatchCounts({"00": 3}, {"00": 2}),
        BatchCounts({"00": 4, "01": -1}, {"00": 3}),
    ],
    ids=["backend_exception", "incomplete_ideal", "incomplete_noisy", "negative_counts"],
)
def test_failed_batch_preserves_previous_counts_blocks_dependents_and_continues(failure):
    phase, _, main = make_phase(outcomes={2: failure})
    jobs = {name: make_job(name, shots, order=order)
            for order, (name, shots) in enumerate([("A", 2), ("B", 5), ("C", 1), ("D", 1)])}
    jobs["C"].depends_on = [jobs["B"].job_information]

    result = execute(phase, make_machines(machine=4), jobs)

    assert_success(result["A"], 2)
    assert_success(result["D"], 1)
    assert result["B"].status == "FAILED"
    assert result["B"].error_reason
    assert result["B"].requested_shots == 5
    assert result["B"].completed_shots == 2
    assert result["B"].distribution_no_noise == {"00": 2}
    assert result["B"].distribution_with_noise == {"00": 2}
    assert result["B"].fidelity is None
    assert result["B"].execution_time == result["B"].end_time == 5
    assert result["C"].status == "BLOCKED"
    assert result["C"].start_time is result["C"].end_time is None
    assert result["C"].completed_shots == 0
    assert result["C"].error_reason
    assert result["D"].start_time == 5
    assert len(main.calls) == 3
    summary = phase.execution_summary
    assert (summary.succeeded_jobs, summary.failed_jobs, summary.blocked_jobs) == (2, 1, 1)
    assert [batch.status for batch in summary.batches] == ["SUCCEEDED", "FAILED", "SUCCEEDED"]
    assert summary.makespan == 6


def test_preparation_failure_uses_zero_virtual_time_and_fails_all_members():
    phase, preparation, main = make_phase(fail_preparation=[1])
    jobs = {name: make_job(name, 1, order=order) for order, name in enumerate("ABCD")}
    jobs["C"].depends_on = [jobs["A"].job_information]

    result = execute(phase, make_machines(machine=4), jobs)

    assert result["A"].status == result["B"].status == "FAILED"
    assert result["A"].start_time is result["A"].end_time is None
    assert result["B"].start_time is result["B"].end_time is None
    assert result["A"].completed_shots == result["B"].completed_shots == 0
    assert result["C"].status == "BLOCKED"
    assert_success(result["D"], 1)
    assert result["D"].start_time == 0
    assert len(preparation.calls) == 2
    assert len(main.calls) == 1
    assert phase.execution_summary.makespan == 1
    failed_batch = phase.execution_summary.batches[0]
    assert failed_batch.status == "FAILED"
    assert failed_batch.start_time == failed_batch.end_time == 0


def test_blocking_propagates_transitively_even_before_future_arrival():
    phase, _, _ = make_phase(outcomes={1: RuntimeError("backend offline")})
    jobs = {
        "A": make_job("A"),
        "B": make_job("B", order=1, arrival=100),
        "C": make_job("C", order=2, arrival=200),
    }
    jobs["B"].depends_on = [jobs["A"].job_information]
    jobs["C"].depends_on = [jobs["B"].job_information]

    result = execute(phase, make_machines(machine=2), jobs)

    assert [job.status for job in result.values()] == ["FAILED", "BLOCKED", "BLOCKED"]
    assert phase.execution_summary.makespan == 1


def test_summary_metrics_use_virtual_intervals_and_include_idle_machines():
    phase, _, _ = make_phase()
    capture = ResultOfSchedule(nameSchedule="kept", ScheduleLatency=0.123)
    jobs = {"A": make_job("A", 2), "B": make_job("B", 3, arrival=1, order=1)}

    result = execute(
        phase, make_machines(machine=2, idle=4), jobs, capture_result_schedule=capture,
    )

    assert result["B"].start_time == 2
    summary = phase.execution_summary
    assert summary.makespan == 5
    assert summary.total_turnaround_time == 6
    assert summary.average_turnaround_time == 3
    assert summary.total_waiting_time == summary.total_response_time == 1
    assert summary.average_waiting_time == summary.average_response_time == 0.5
    assert summary.job_completion_rate == pytest.approx(0.4)
    assert summary.average_fidelity == pytest.approx(1)
    assert summary.machines["machine"].busy_time == 5
    assert summary.machines["machine"].qubit_time == 10
    assert summary.machines["machine"].utilization == 1
    assert summary.machines["idle"].utilization == 0
    assert capture.execution_summary is summary
    assert capture.nameSchedule == "kept"
    assert capture.ScheduleLatency == 0.123


def test_empty_execution_resets_the_report_without_changing_previous_report():
    phase, _, main = make_phase()
    machines = make_machines(machine=2)
    execute(phase, machines, {"A": make_job("A", 3)})
    previous_summary = phase.execution_summary

    result = execute(phase, machines, {})

    assert result == {}
    assert phase.execution_summary is not previous_summary
    assert previous_summary.makespan == 3
    assert phase.execution_summary.makespan == 0
    assert phase.execution_summary.batches == []
    assert phase.execution_summary.succeeded_jobs == 0
    assert phase.execution_summary.failed_jobs == phase.execution_summary.blocked_jobs == 0
    assert phase.execution_summary.average_fidelity == 0
    assert phase.execution_summary.job_completion_rate == 0
    assert phase.execution_summary.machines["machine"].utilization == 0
    assert len(main.calls) == 1
    assert execute(phase, {}, {}) == {}


@pytest.mark.parametrize("shots", [0, -1, 1.5, True, "10"])
def test_invalid_shots_rejected_before_preparation(shots):
    phase, preparation, main = make_phase()
    with pytest.raises(ValueError, match="shot"):
        execute(phase, make_machines(machine=2), {"A": make_job("A", shots)})
    assert preparation.calls == main.calls == []


@pytest.mark.parametrize("arrival", [-1, float("nan"), float("inf"), "later"])
def test_invalid_arrival_rejected_before_preparation(arrival):
    phase, preparation, main = make_phase()
    with pytest.raises(ValueError, match="arrival"):
        execute(phase, make_machines(machine=2), {"A": make_job("A", arrival=arrival)})
    assert preparation.calls == main.calls == []


@pytest.mark.parametrize("order", [None, -1, 0.5, True])
def test_invalid_dispatch_order_rejected_before_preparation(order):
    phase, preparation, main = make_phase()
    with pytest.raises(ValueError, match="dispatch"):
        execute(phase, make_machines(machine=2), {"A": make_job("A", order=order)})
    assert preparation.calls == main.calls == []


@pytest.mark.parametrize(
    "invalid_input",
    ["missing_information", "missing_circuit", "unbound_parameters", "no_measurements",
     "unknown_machine", "duplicate_order", "width_mismatch", "exceeds_capacity",
     "zero_capacity", "capacity_exceeds_backend", "unknown_dependency", "equal_dependency_clone",
     "self_dependency", "dependency_cycle"],
)
def test_invalid_workloads_fail_before_any_batch_is_prepared(invalid_input):
    phase, preparation, main = make_phase()
    machines = make_machines(machine=4)
    jobs = {"A": make_job("A"), "B": make_job("B", order=1)}
    information = jobs["A"].job_information
    if invalid_input == "missing_information":
        jobs["A"].job_information = None
    elif invalid_input == "missing_circuit":
        information.circuit = None
    elif invalid_input == "unbound_parameters":
        information.circuit.rx(Parameter("theta"), 0)
    elif invalid_input == "no_measurements":
        information.circuit = QuantumCircuit(2, 2)
    elif invalid_input == "unknown_machine":
        jobs["A"].assigned_machine = "missing"
    elif invalid_input == "duplicate_order":
        jobs["B"].dispatch_order = 0
    elif invalid_input == "width_mismatch":
        information.num_qubits = 3
    elif invalid_input == "exceeds_capacity":
        machines["machine"].capacity = 1
    elif invalid_input == "zero_capacity":
        machines["machine"].capacity = 0
    elif invalid_input == "capacity_exceeds_backend":
        machines["machine"].capacity = 5
    elif invalid_input == "unknown_dependency":
        jobs["B"].depends_on = [JobInfo(job_name="not submitted")]
    elif invalid_input == "equal_dependency_clone":
        jobs["B"].depends_on = [JobInfo(**vars(information))]
    elif invalid_input == "self_dependency":
        jobs["A"].depends_on = [information]
    elif invalid_input == "dependency_cycle":
        jobs["A"].depends_on = [jobs["B"].job_information]
        jobs["B"].depends_on = [information]

    with pytest.raises(ValueError) as error:
        execute(phase, machines, jobs)

    assert str(error.value)
    assert preparation.calls == main.calls == []


def test_strict_queue_cycle_is_rejected_but_backfill_can_run_the_dependency_first():
    phase, preparation, main = make_phase()
    jobs = {"A": make_job("A"), "B": make_job("B", order=1)}
    jobs["A"].depends_on = [jobs["B"].job_information]

    with pytest.raises(ValueError, match="cycl"):
        execute(phase, make_machines(machine=4), jobs)
    assert preparation.calls == main.calls == []

    result = execute(phase, make_machines(machine=4), jobs, queue_policy="backfill")
    assert result["B"].start_time == 0
    assert result["A"].start_time == result["B"].end_time == 1


def test_strict_queue_cycle_can_span_machines_without_a_dependency_only_cycle():
    phase, preparation, main = make_phase()
    machines = make_machines(first=4, second=4)
    jobs = {
        "A": make_job("A", machine="first"),
        "B": make_job("B", machine="first", order=1),
        "C": make_job("C", machine="second"),
        "D": make_job("D", machine="second", order=1),
    }
    jobs["A"].depends_on = [jobs["D"].job_information]
    jobs["C"].depends_on = [jobs["B"].job_information]

    with pytest.raises(ValueError, match="cycl"):
        execute(phase, machines, jobs)
    assert preparation.calls == main.calls == []

    result = execute(phase, machines, jobs, queue_policy="backfill")
    assert result["B"].start_time == result["D"].start_time == 0
    assert result["A"].start_time == result["C"].start_time == 1


def test_dependency_identity_distinguishes_equal_jobs_with_duplicate_embedded_names():
    phase, _, _ = make_phase()
    first = make_job("duplicate", 1)
    equal_job = JobInfo(**vars(first.job_information))
    jobs = {
        "first key": first,
        "second key": SchedulerJobInfo(equal_job, "machine", 1, [first.job_information]),
    }

    result = execute(phase, make_machines(machine=4), jobs)

    assert list(result) == ["first key", "second key"]
    assert result["first key"].start_time == 0
    assert result["second key"].start_time == 1
    assert result["second key"].job_info is equal_job


def test_invalid_queue_policy_rejected_before_preparation():
    phase, preparation, main = make_phase()
    with pytest.raises(ValueError, match="queue_policy"):
        execute(phase, make_machines(machine=2), {"A": make_job("A")}, queue_policy="fifo-ish")
    assert preparation.calls == main.calls == []
