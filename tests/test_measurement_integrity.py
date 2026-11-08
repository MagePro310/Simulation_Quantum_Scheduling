"""Tests that simulation metrics are repeatable and account for every submitted job."""

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark

from source.flow.execution.circuit_composer import CircuitPreparation
from source.flow.execution.metrics_calculator import MetricsCalculator
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.execution.reconstruction_handler import ReconstructionHandler
from source.flow.runner import run_pipeline
from source.flow.schedule.schedule_phase import SchedulePhase
from source.algorithm.heuristic.ffd import FFD
from source.models.job import ExecutionResult, JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.schedule_result import ExecutionSummary, ResultOfSchedule
from source.models.simulation_config import (
    ExecutionConfig,
    SimulationConfig,
    WorkloadConfig,
)
from source.simulator import FakeBelemV2, FakeBogotaV2


def _cut_workload_config(seed: int) -> SimulationConfig:
    """A workload where one job must be cut, so both execution paths run."""
    return SimulationConfig(
        workload=WorkloadConfig(
            benchmark="ghz",
            jobs={
                "small": {"qubits": 2, "shots": 256},
                "large": {"qubits": 7, "shots": 256},
            },
        ),
        machines=["FakeBelemV2", "FakeBogotaV2"],
        execution=ExecutionConfig(seed=seed),
    )


def _fidelity(seed: int) -> float:
    result = run_pipeline("FFD", config=_cut_workload_config(seed))
    return result["execution_summary"]["average_fidelity"]


@pytest.mark.parametrize("seed", [0, 11])
def test_same_seed_gives_identical_fidelity(seed):
    assert _fidelity(seed=seed) == _fidelity(seed=seed)


def test_different_seed_changes_fidelity():
    assert _fidelity(seed=11) != _fidelity(seed=12)


def _cut_child(parent: JobInfo, label: str, start: float, end: float) -> ExecutionResult:
    child = JobInfo(job_name=f"{parent.job_name}_sub_{label}", parent_job=parent)
    return ExecutionResult(
        job_info=child,
        status="SUCCEEDED",
        start_time=start,
        end_time=end,
        execution_time=end - start,
    )


def test_cut_job_waiting_time_counts_overlapping_subcircuits_once(monkeypatch):
    """Timeline from a QGroup run: both pieces start late and then overlap."""
    parent = JobInfo(job_name="job4", arrival_time=0.0, shots=1024)
    results = {
        "job4_sub_A": _cut_child(parent, "A", 0.00642, 0.06101),
        "job4_sub_B": _cut_child(parent, "B", 0.00608, 0.0549),
    }
    monkeypatch.setattr(
        "source.flow.execution.reconstruction_handler.CircuitReconstructor.reconstruct_distribution",
        lambda ctx, shots, seed: ({}, {}, 1.0, 0.0, 1.0),
    )

    ReconstructionHandler.reconstruct_parent_job(parent, results)

    summary = ExecutionSummary()
    MetricsCalculator.calculate_metrics(summary, results, machines={}, now=0.06101)
    assert summary.average_waiting_time == pytest.approx(0.00608)


def test_cut_job_waiting_time_includes_gap_between_subcircuits(monkeypatch):
    parent = JobInfo(job_name="job", arrival_time=0.0, shots=1024)
    results = {
        "job_sub_A": _cut_child(parent, "A", 0.0, 1.0),
        "job_sub_B": _cut_child(parent, "B", 3.0, 5.0),
    }
    monkeypatch.setattr(
        "source.flow.execution.reconstruction_handler.CircuitReconstructor.reconstruct_distribution",
        lambda ctx, shots, seed: ({}, {}, 1.0, 0.0, 1.0),
    )

    ReconstructionHandler.reconstruct_parent_job(parent, results)

    summary = ExecutionSummary()
    MetricsCalculator.calculate_metrics(summary, results, machines={}, now=5.0)
    assert summary.average_waiting_time == pytest.approx(2.0)


def _machines() -> dict[str, MachineCharacteristic]:
    return {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }


def _ghz_job(name: str, qubits: int) -> JobInfo:
    circuit = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=qubits)
    return JobInfo(job_name=name, circuit=circuit, num_qubits=qubits, shots=256)


def test_failed_subcircuit_is_counted_against_parent_job(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("injected subcircuit failure")

    monkeypatch.setattr(CircuitPreparation, "compose_joint_cutting_batch", staticmethod(fail))

    origin_jobs = {"small": _ghz_job("small", 2), "large": _ghz_job("large", 7)}
    machines = _machines()
    capture = ResultOfSchedule()
    scheduled = SchedulePhase(algorithm=FFD()).execute(origin_jobs, machines, capture)
    results = ExecutionPhase().execute(machines, scheduled, capture_result_schedule=capture)

    assert results["large"].status == "FAILED"
    assert "injected subcircuit failure" in results["large"].error_reason
    summary = capture.execution_summary
    assert summary.failed_jobs >= 1
    assert summary.succeeded_jobs + summary.failed_jobs + summary.blocked_jobs == len(origin_jobs)


def test_blocked_subcircuits_mark_parent_blocked():
    parent = JobInfo(job_name="job", shots=1024)
    results = {
        "job_sub_A": ExecutionResult(
            job_info=JobInfo(job_name="job_sub_A", parent_job=parent), status="BLOCKED"
        ),
    }

    ReconstructionHandler.finalize_unreconstructed_parents(results)

    assert results["job"].status == "BLOCKED"


def test_transpile_failure_is_recorded_as_failed_batch(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("injected transpile failure")

    monkeypatch.setattr(CircuitPreparation, "prepare_batch", fail)

    job = _ghz_job("only", 2)
    scheduled = {
        "only": SchedulerJobInfo(job_information=job, assigned_machine="belem", dispatch_order=0)
    }
    capture = ResultOfSchedule()
    results = ExecutionPhase().execute(_machines(), scheduled, capture_result_schedule=capture)

    assert results["only"].status == "FAILED"
    assert "injected transpile failure" in results["only"].error_reason
    assert capture.execution_summary.failed_jobs == 1
