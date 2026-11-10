"""QGroup follows its paper: calibrated per-shot runtimes, EPST from calibration data,
and execution that follows the BILP matrix X workload by workload."""

from math import prod

import numpy as np
import pytest

from source.algorithm.heuristic.qgroup import QGroup, QGroupJob, QGroupMachine, QGroupSchedule, _workload_segments
from source.flow.execution import SilentTimelineReporter
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.input.benchmark_circuits import load_benchmark_circuit
from source.flow.schedule.cutting import SchedulingCutterHelper
from source.flow.schedule.schedule_phase import SchedulePhase
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.schedule_result import ResultOfSchedule
from source.simulator import FakeBelemV2


def _job(name: str, benchmark: str, qubits: int, shots: int = 1024) -> SchedulerJobInfo:
    circuit = load_benchmark_circuit(benchmark, qubits)
    return SchedulerJobInfo(job_information=JobInfo(
        job_name=name, circuit=circuit, num_qubits=circuit.num_qubits, shots=shots, arrival_time=0,
    ))


def _belem() -> dict[str, MachineCharacteristic]:
    return {"belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5)}


def _bound(jobs, machines) -> QGroup:
    algorithm = QGroup()
    algorithm.bind(jobs, machines)
    return algorithm


def test_runtime_adds_up_calibrated_gate_durations():
    jobs = {"ghz": _job("ghz", "ghz", 3), "grover": _job("grover", "grover", 3)}
    machines = _belem()
    algorithm = _bound(jobs, machines)
    machine = QGroupMachine(id="belem", qubits=5, type_key="belem")
    ghz = algorithm._runtime_callback(QGroupJob("ghz", 3, 1024), machine)
    grover = algorithm._runtime_callback(QGroupJob("grover", 3, 1024), machine)
    assert 1e-6 < ghz < grover  # microseconds per shot; the deeper circuit takes longer


def test_cut_subcircuit_runtime_counts_every_subexperiment():
    parent = _job("big", "ghz", 7).job_information
    fragments = SchedulingCutterHelper.cut_job(parent, cluster_sizes=[5, 2])
    machines = _belem()
    algorithm = _bound(fragments, machines)
    machine = QGroupMachine(id="belem", qubits=5, type_key="belem")
    info = fragments["big_sub_B"].job_information
    single = {"one": _job("one", "ghz", 2)}
    single["one"].job_information.circuit = info.subexperiments[0]
    one_circuit = _bound(single, machines)._runtime_callback(QGroupJob("one", 2, 1024), machine)
    assert algorithm._runtime_callback(QGroupJob("big_sub_B", 2, 1024), machine) == pytest.approx(
        len(info.subexperiments) * one_circuit
    )


def test_epst_is_the_product_of_operation_success_probabilities():
    jobs = {"a": _job("a", "ghz", 3)}
    machines = _belem()
    algorithm = _bound(jobs, machines)
    epst = algorithm._workload_epst("belem", frozenset({"a"}))["a"]

    backend = machines["belem"].quantum_machine
    compiled = algorithm._compiled(machines["belem"], {"a": jobs["a"].job_information}).transpiled_circuit
    expected = prod(
        1 - (backend.target[i.operation.name][tuple(compiled.find_bit(q).index for q in i.qubits)].error or 0)
        for i in compiled.data
        if i.operation.name not in ("delay", "barrier")
    )
    assert 0 < epst <= 1
    assert epst == pytest.approx(expected)


def test_workload_segments_follow_changes_of_the_running_set():
    X = np.array([[1, 1, 1, 0], [1, 0, 0, 0], [0, 1, 1, 1]], dtype=np.int8)
    jobs = tuple(QGroupJob(n, 1, 1) for n in "abc")
    sched = QGroupSchedule(jobs, 1, (3, 1, 3), X, X, X[0], X[0], 0.0, True, "test")
    assert _workload_segments(sched) == [([0, 1], 1), ([0, 2], 2), ([2], 1)]


def test_execution_follows_the_workloads_of_x():
    jobs = {
        "long": _job("long", "ghz", 3, shots=2048),
        "s1": _job("s1", "ghz", 2, shots=1024),
        "s2": _job("s2", "ghz", 2, shots=1024),
    }
    machines = _belem()
    capture = ResultOfSchedule()
    origin = {name: job.job_information for name, job in jobs.items()}
    scheduled = SchedulePhase(algorithm=QGroup()).execute(origin, machines, capture)

    # Every piece belongs to one workload; shards of a job add up to its shots
    shots_by_job: dict[str, int] = {}
    for name, piece in scheduled.items():
        root = piece.job_information.shot_parent or piece.job_information
        shots_by_job[root.job_name] = shots_by_job.get(root.job_name, 0) + piece.job_information.shots
    assert shots_by_job == {"long": 2048, "s1": 1024, "s2": 1024}

    # Each workload waits for the previous one on its machine
    for piece in scheduled.values():
        for dependency in piece.depends_on or []:
            earlier = next(p for p in scheduled.values() if p.job_information is dependency)
            assert earlier.dispatch_order == piece.dispatch_order - 1

    phase = ExecutionPhase(reporter=SilentTimelineReporter())
    results = phase.execute(machines, scheduled, seed=1)
    summary = phase.execution_summary
    assert (summary.succeeded_jobs, summary.failed_jobs) == (3, 0)
    assert all(results[name].completed_shots == shots for name, shots in shots_by_job.items())
    # One batch per workload: batches run in dispatch order
    orders = sorted({p.dispatch_order for p in scheduled.values()})
    assert len(summary.batches) == len(orders)


def test_job_spanning_two_workloads_runs_as_two_shards_and_merges():
    """X: 'long' runs in bins 0-1, 's1' joins it in bin 0, 's2' in bin 1."""
    from source.algorithm.heuristic.qgroup import QGroupAssignment, QGroupPlan

    jobs = {
        "long": _job("long", "ghz", 3, shots=2048),
        "s1": _job("s1", "ghz", 2, shots=1024),
        "s2": _job("s2", "ghz", 2, shots=1024),
    }
    machines = _belem()
    X = np.array([[1, 1], [1, 0], [0, 1]], dtype=np.int8)
    qjobs = tuple(QGroupJob(n, jobs[n].job_information.num_qubits, jobs[n].job_information.shots) for n in jobs)
    sched = QGroupSchedule(qjobs, 1024, (2, 1, 1), X, X, X[0], X[0], 1.0, True, "test")
    machine = QGroupMachine(id="belem", qubits=5, type_key="belem")
    plan = QGroupPlan({"belem": [QGroupAssignment(machine, sched, 0.0, 1.0)]})

    scheduled = QGroup()._apply_plan(plan, jobs, machines)
    assert sorted(scheduled) == ["long_shot0", "long_shot1", "s1", "s2"]
    assert {n: (p.job_information.shots, p.dispatch_order) for n, p in scheduled.items()} == {
        "long_shot0": (1024, 0), "s1": (1024, 0), "long_shot1": (1024, 1), "s2": (1024, 1),
    }

    phase = ExecutionPhase(reporter=SilentTimelineReporter())
    results = phase.execute(machines, scheduled, seed=1)
    assert [sorted(b.job_ids) for b in phase.execution_summary.batches] == [
        ["long_shot0", "s1"], ["long_shot1", "s2"],
    ]
    assert results["long"].status == "SUCCEEDED" and results["long"].completed_shots == 2048
    assert phase.execution_summary.succeeded_jobs == 3
