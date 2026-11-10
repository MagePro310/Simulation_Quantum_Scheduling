"""Tests for the Cut&Shoot algorithm: cut, allocate fragment shots, split fairly, merge."""

from collections import defaultdict

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark

from source.algorithm.heuristic.cut_and_shoot import CutAndShoot
from source.algorithm.registry import get_algorithm, list_algorithms
from source.flow.runner import run_pipeline
from source.flow.schedule.schedule_phase import SchedulePhase
from source.models.job import JobInfo
from source.models.machine import MachineCharacteristic
from source.models.schedule_result import ResultOfSchedule
from source.models.simulation_config import ExecutionConfig, SimulationConfig, WorkloadConfig
from source.simulator import FakeBelemV2, FakeBogotaV2, FakeJakartaV2


def _ghz(name: str, qubits: int, shots: int = 1024) -> JobInfo:
    circuit = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=qubits)
    return JobInfo(job_name=name, circuit=circuit, num_qubits=qubits, shots=shots, arrival_time=0)


def _two_machines():
    return {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }


def _schedule(algorithm, jobs, machines):
    capture = ResultOfSchedule()
    scheduled = SchedulePhase(algorithm=algorithm).execute(jobs, machines, capture)
    return scheduled, capture


def test_registered_under_one_name():
    assert "CutAndShoot" in list_algorithms()
    assert isinstance(get_algorithm("CutAndShoot"), CutAndShoot)


def test_every_fragment_is_split_fairly_over_all_machines():
    jobs = {"a": _ghz("a", 3), "b": _ghz("b", 7)}
    scheduled, capture = _schedule(CutAndShoot(), jobs, _two_machines())

    assert capture.shot_distribution is True
    shards_by_fragment = defaultdict(list)
    for name, s_job in scheduled.items():
        info = s_job.job_information
        assert info.shot_parent is not None, f"{name} was not split"
        assert s_job.assigned_machine in {"belem", "bogota"}
        shards_by_fragment[info.shot_parent.job_name].append(s_job)

    # a (3q) is cut into halves, b (7q) is cut by PreSchedule: 4 fragments in all
    assert set(shards_by_fragment) == {"a_sub_A", "a_sub_B", "b_sub_A", "b_sub_B"}
    for shards in shards_by_fragment.values():
        assert sorted(s.assigned_machine for s in shards) == ["belem", "bogota"]
        assert sorted(s.job_information.shots for s in shards) == [512, 512]


def test_dispatch_order_is_fifo_per_machine():
    jobs = {"first": _ghz("first", 3), "second": _ghz("second", 3)}
    scheduled, _ = _schedule(CutAndShoot(), jobs, _two_machines())

    for machine in ("belem", "bogota"):
        queue = sorted(
            (s for s in scheduled.values() if s.assigned_machine == machine),
            key=lambda s: s.dispatch_order,
        )
        assert [s.dispatch_order for s in queue] == list(range(len(queue)))
        roots = [s.job_information.shot_parent.parent_job.job_name for s in queue]
        assert roots == sorted(roots, key=["first", "second"].index)


def test_fragment_only_goes_to_machines_that_fit_it():
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "jakarta": MachineCharacteristic(name="jakarta", quantum_machine=FakeJakartaV2(), capacity=7),
    }
    jobs = {"wide": _ghz("wide", 6), "narrow": _ghz("narrow", 3)}
    scheduled, _ = _schedule(CutAndShoot(cut_all=False), jobs, machines)

    assert scheduled["wide"].assigned_machine == "jakarta"  # 6 qubits fit only jakarta: not split
    narrow = [s for s in scheduled.values() if s.job_information.shot_parent is not None]
    assert sorted(s.assigned_machine for s in narrow) == ["belem", "jakarta"]


@pytest.mark.parametrize(
    ("policy", "expected"),
    [("multiplier", [1024, 1024]), ("divider", [512, 512]), ("qubit_proportional", [512, 512])],
)
def test_fragment_shot_policies(policy, expected):
    scheduled, _ = _schedule(
        CutAndShoot(fragment_shot_policy=policy, shot_wise=False), {"j": _ghz("j", 4)}, _two_machines()
    )
    assert sorted(s.job_information.shots for s in scheduled.values()) == expected


def test_without_shot_wise_jobs_run_whole_on_least_loaded_machine():
    jobs = {"a": _ghz("a", 2), "b": _ghz("b", 2)}
    scheduled, capture = _schedule(CutAndShoot(cut_all=False, shot_wise=False), jobs, _two_machines())

    assert capture.shot_distribution is False
    assert {s.assigned_machine for s in scheduled.values()} == {"belem", "bogota"}


def test_unknown_policies_rejected():
    with pytest.raises(ValueError):
        CutAndShoot(fragment_shot_policy="nope")
    with pytest.raises(ValueError):
        CutAndShoot(split_policy="hellinger")


def _config(seed: int) -> SimulationConfig:
    return SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={"small": {"qubits": 3, "shots": 512}, "large": {"qubits": 7, "shots": 512}},
        ),
        machines=["FakeBelemV2", "FakeBogotaV2"],
        execution=ExecutionConfig(seed=seed),
    )


def test_end_to_end_reconstructs_every_job_reproducibly():
    first = run_pipeline("CutAndShoot", config=_config(seed=3))
    second = run_pipeline("CutAndShoot", config=_config(seed=3))

    summary = first["execution_summary"]
    assert (summary["succeeded_jobs"], summary["failed_jobs"], summary["blocked_jobs"]) == (2, 0, 0)
    assert first["shot_distribution"] is True
    assert {b["machine_name"] for b in summary["batches"]} == {"fake_belem", "fake_bogota"}
    assert 0.0 < summary["average_fidelity"] <= 1.0
    assert summary["average_fidelity"] == second["execution_summary"]["average_fidelity"]
