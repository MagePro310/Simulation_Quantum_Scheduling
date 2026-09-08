import pytest
from qiskit import QuantumCircuit

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


def make_jobs(**widths):
    return {
        name: SchedulerJobInfo(JobInfo(job_name=name, num_qubits=width))
        for name, width in widths.items()
    }


def make_machines(**capacities):
    return {
        name: MachineCharacteristic(name=name, quantum_machine=object(), capacity=capacity)
        for name, capacity in capacities.items()
    }


def test_pack_sorts_decreasing_and_preserves_first_fit_and_tie_order():
    jobs = make_jobs(small=2, tied_first=3, largest=8, tied_second=3)
    bins = FFD().pack(jobs, make_machines(first=10, tighter_fit=8))

    assert [(bin.machine_name, list(bin.jobs), bin.used_qubits) for bin in bins] == [
        ("first", ["largest", "small"], 10),
        ("tighter_fit", ["tied_first", "tied_second"], 6),
    ]
    assert list(jobs) == ["small", "tied_first", "largest", "tied_second"]


def test_pack_reuses_remaining_capacity_in_earlier_rounds():
    jobs = make_jobs(first=6, second=6, third=4, fourth=4)
    jobs["first"].assigned_machine = "previous_machine"
    jobs["first"].dispatch_order = 8
    dependencies = [JobInfo(job_name="existing_dependency", num_qubits=1)]
    jobs["first"].depends_on = dependencies
    before = {name: vars(job).copy() for name, job in jobs.items()}
    machines = make_machines(machine=10)
    bins = FFD().pack(jobs, machines)

    assert [(bin.round_index, list(bin.jobs)) for bin in bins] == [
        (0, ["first", "third"]),
        (1, ["second", "fourth"]),
    ]
    assert all(bin.used_qubits == bin.num_qubits == 10 for bin in bins)
    assert bins[0].jobs is not bins[1].jobs
    assert {name: vars(job) for name, job in jobs.items()} == before
    assert jobs["first"].depends_on is dependencies
    assert all(not hasattr(job, "scheduled_start_time") for job in jobs.values())
    assert all(not hasattr(job, "scheduled_end_time") for job in jobs.values())
    assert vars(machines["machine"]).keys() == {"name", "quantum_machine", "capacity"}
    assert machines["machine"].capacity == 10


def test_pack_closes_full_bins_before_remaining_open_bins():
    bins = FFD().pack(make_jobs(earlier_partial=6, later_a=5, later_b=5), make_machines(machine=10))

    assert [(bin.round_index, list(bin.jobs), bin.used_qubits) for bin in bins] == [
        (1, ["later_a", "later_b"], 10),
        (0, ["earlier_partial"], 6),
    ]


def test_pack_creates_complete_fresh_machine_lists():
    bins = FFD().pack(make_jobs(first=8, second=8), make_machines(large=10, small=3))

    assert [(bin.machine_name, bin.round_index, bin.used_qubits) for bin in bins] == [
        ("large", 0, 8), ("small", 0, 0), ("large", 1, 8), ("small", 1, 0),
    ]
    assert len({id(bin.jobs) for bin in bins}) == 4
    assert all(bin.used_qubits <= bin.num_qubits for bin in bins)


def test_empty_input_preserves_initial_empty_bins():
    jobs = {}
    bins = FFD().pack(jobs, make_machines(first=5, second=7))

    assert [(bin.machine_name, bin.round_index, bin.jobs) for bin in bins] == [
        ("first", 0, {}), ("second", 0, {}),
    ]
    assert FFD().pack(jobs, {}) == []
    assert FFD().execute(jobs, {}) is jobs


def test_pack_uses_circuit_width_when_explicit_width_is_missing():
    jobs = {"circuit_only": SchedulerJobInfo(JobInfo(circuit=QuantumCircuit(3)))}
    bins = FFD().pack(jobs, make_machines(machine=3))

    assert bins[0].used_qubits == 3
    assert bins[0].jobs["circuit_only"] is jobs["circuit_only"]


def test_execute_dispatches_earlier_round_before_later_closed_bin():
    jobs = make_jobs(earlier_partial=6, later_a=5, later_b=5)
    for job, shots in zip(jobs.values(), [2, 3, 7]):
        job.job_information.shots = shots
    jobs["earlier_partial"].job_information.arrival_time = 10

    result = FFD().execute(jobs, make_machines(machine=10))

    assert result is jobs
    assert [job.dispatch_order for job in jobs.values()] == [0, 1, 2]
    assert jobs["earlier_partial"].depends_on == []
    for name in ["later_a", "later_b"]:
        assert len(jobs[name].depends_on) == 1
        assert jobs[name].depends_on[0] is jobs["earlier_partial"].job_information
    assert all(job.assigned_machine == "machine" for job in jobs.values())
    assert all(not hasattr(job, "scheduled_start_time") for job in jobs.values())
    assert all(not hasattr(job, "scheduled_end_time") for job in jobs.values())


def test_execute_keeps_jobs_in_same_bin_independent_despite_different_durations_and_arrivals():
    deep_circuit = QuantumCircuit(2)
    for _ in range(3):
        deep_circuit.x(0)
    shallow_circuit = QuantumCircuit(2)
    shallow_circuit.x(0)
    jobs = {
        "deep": SchedulerJobInfo(JobInfo(num_qubits=2, circuit=deep_circuit, shots=2, arrival_time=3)),
        "many_shots": SchedulerJobInfo(JobInfo(num_qubits=2, circuit=shallow_circuit, shots=10, arrival_time=7)),
    }

    FFD().execute(jobs, make_machines(machine=4))

    assert [job.dispatch_order for job in jobs.values()] == [0, 1]
    assert all(job.depends_on == [] for job in jobs.values())
    assert all(job.assigned_machine == "machine" for job in jobs.values())


def test_execute_accepts_default_shots_and_keeps_separate_machines_independent():
    jobs = make_jobs(first=5, second=5)

    FFD().execute(jobs, make_machines(first_machine=5, second_machine=5))

    assert [job.assigned_machine for job in jobs.values()] == ["first_machine", "second_machine"]
    assert [job.dispatch_order for job in jobs.values()] == [0, 0]
    assert all(job.depends_on == [] for job in jobs.values())


def test_dictionary_keys_are_canonical_and_explicit_width_overrides_circuit():
    job = SchedulerJobInfo(JobInfo(
        job_name="embedded_job_name", num_qubits=2, circuit=QuantumCircuit(5), shots=3,
    ))
    jobs = {"job_key": job}
    machine = MachineCharacteristic(name="embedded_machine_name", quantum_machine=object(), capacity=2)
    machines = {"machine_key": machine}

    bins = FFD().pack(jobs, machines)

    assert bins[0].machine_name == "machine_key"
    assert bins[0].used_qubits == 2
    assert list(bins[0].jobs) == ["job_key"]
    assert bins[0].jobs["job_key"] is job

    assert FFD().execute(jobs, machines) is jobs
    assert job.assigned_machine == "machine_key"
    assert job.dispatch_order == 0
    assert job.depends_on == []
    assert job.job_information.job_name == "embedded_job_name"
    assert machine.name == "embedded_machine_name"


def test_execute_orders_jobs_and_links_previous_bins_independently_per_machine():
    jobs = make_jobs(first=6, second=6, third=4, fourth=2, fifth=2)
    for job, shots in zip(jobs.values(), [7, 3, 2, 5, 1]):
        job.job_information.shots = shots
        job.dispatch_order = 99
    dependencies = [jobs["third"].job_information]
    jobs["fourth"].depends_on = dependencies

    FFD().execute(jobs, make_machines(small=4, large=6))

    assert {
        name: (job.assigned_machine, job.dispatch_order)
        for name, job in jobs.items()
    } == {
        "first": ("large", 0),
        "second": ("large", 1),
        "third": ("small", 0),
        "fourth": ("small", 1),
        "fifth": ("small", 2),
    }
    assert jobs["first"].depends_on == jobs["third"].depends_on == []
    assert len(jobs["second"].depends_on) == 1
    assert jobs["second"].depends_on[0] is jobs["first"].job_information
    for name in ["fourth", "fifth"]:
        assert len(jobs[name].depends_on) == 1
        assert jobs[name].depends_on[0] is jobs["third"].job_information


def test_each_bin_depends_on_all_jobs_from_immediately_previous_bin():
    jobs = make_jobs(first=5, second=5, third=5, fourth=5, fifth=5)

    FFD().execute(jobs, make_machines(machine=10))

    assert [job.dispatch_order for job in jobs.values()] == [0, 1, 2, 3, 4]
    assert jobs["first"].depends_on == jobs["second"].depends_on == []
    for name in ["third", "fourth"]:
        assert [id(dependency) for dependency in jobs[name].depends_on] == [
            id(jobs["first"].job_information), id(jobs["second"].job_information),
        ]
    assert [id(dependency) for dependency in jobs["fifth"].depends_on] == [
        id(jobs["third"].job_information), id(jobs["fourth"].job_information),
    ]


def test_execute_merges_dependencies_by_identity_and_is_idempotent():
    # Equal dataclass values still represent distinct prerequisite jobs.
    first = JobInfo(num_qubits=2, shots=1)
    second = JobInfo(num_qubits=2, shots=1)
    external = JobInfo(num_qubits=2, shots=1)
    jobs = {
        "first": SchedulerJobInfo(first, depends_on=[external]),
        "second": SchedulerJobInfo(second),
        "later": SchedulerJobInfo(JobInfo(num_qubits=2), depends_on=[external, first, first]),
    }
    machines = make_machines(machine=4)
    original_fields = {name: set(vars(job)) for name, job in jobs.items()}
    algorithm = FFD()

    algorithm.execute(jobs, machines)

    assert len(jobs["first"].depends_on) == 1
    assert jobs["first"].depends_on[0] is external
    assert jobs["second"].depends_on == []
    assert [id(dependency) for dependency in jobs["later"].depends_on] == [
        id(external), id(first), id(second),
    ]
    before = {
        name: (job.assigned_machine, job.dispatch_order, tuple(map(id, job.depends_on)))
        for name, job in jobs.items()
    }

    assert algorithm.execute(jobs, machines) is jobs

    assert {
        name: (job.assigned_machine, job.dispatch_order, tuple(map(id, job.depends_on)))
        for name, job in jobs.items()
    } == before
    assert {name: set(vars(job)) for name, job in jobs.items()} == original_fields


@pytest.mark.parametrize("job_info", [None, JobInfo(), JobInfo(num_qubits=3)])
def test_invalid_job_metadata_or_oversized_width_does_not_partially_schedule(job_info):
    jobs = make_jobs(valid=2)
    jobs["invalid"] = SchedulerJobInfo(job_info)
    before = {name: vars(job).copy() for name, job in jobs.items()}

    with pytest.raises(ValueError):
        FFD().execute(jobs, make_machines(machine=2))

    assert {name: vars(job) for name, job in jobs.items()} == before


@pytest.mark.parametrize("invalid_value", [0, -1, 1.5, True])
@pytest.mark.parametrize("field", ["width", "capacity"])
def test_pack_requires_positive_integer_widths_and_capacities(field, invalid_value):
    jobs = make_jobs(job=invalid_value if field == "width" else 1)
    machines = make_machines(machine=invalid_value if field == "capacity" else 2)

    with pytest.raises(ValueError):
        FFD().pack(jobs, machines)


def test_nonempty_jobs_require_a_machine():
    jobs = make_jobs(job=1)

    with pytest.raises(ValueError):
        FFD().execute(jobs, {})

    assert jobs["job"].assigned_machine is None


@pytest.mark.parametrize("invalid_shots", [0, -1, 1.5, True])
def test_invalid_shots_do_not_partially_overwrite_existing_schedule(invalid_shots):
    jobs = make_jobs(valid=2, invalid=2)
    jobs["valid"].job_information.shots = 1
    jobs["invalid"].job_information.shots = invalid_shots
    for job in jobs.values():
        job.assigned_machine = "previous_machine"
        job.dispatch_order = 3
        job.depends_on = [JobInfo(job_name="previous_dependency", num_qubits=1)]
    before = {name: vars(job).copy() for name, job in jobs.items()}

    with pytest.raises(ValueError):
        FFD().execute(jobs, make_machines(machine=2))

    assert {name: vars(job) for name, job in jobs.items()} == before
