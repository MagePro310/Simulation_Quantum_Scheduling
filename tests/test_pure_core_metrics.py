import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from qiskit import QuantumCircuit
from dataclasses import dataclass

from source.component.dataclass.job_info import JobInfo, ExecutionResult, SchedulerJobInfo
from source.component.dataclass.result_schedule import ExecutionSummary
from source.component.dataclass.execution_info import BatchExecutionRecord
from source.flow.execution.metrics_calculator import MetricsCalculator
from source.flow.execution.orchestrator import ConcreteExecutionPhase


def test_qubit_weighted_fidelity_calculation():
    """Verify that average_fidelity is calculated as qubit-weighted mean."""
    summary = ExecutionSummary()

    # Job 1: 2 qubits, fidelity = 0.90
    qc1 = QuantumCircuit(2)
    job1 = JobInfo(job_name="j1", circuit=qc1, num_qubits=2)
    res1 = ExecutionResult(job_info=job1, status="SUCCEEDED", fidelity=0.90, start_time=0.0, end_time=1.0)

    # Job 2: 6 qubits, fidelity = 0.80
    qc2 = QuantumCircuit(6)
    job2 = JobInfo(job_name="j2", circuit=qc2, num_qubits=6)
    res2 = ExecutionResult(job_info=job2, status="SUCCEEDED", fidelity=0.80, start_time=1.0, end_time=2.0)

    results = {"j1": res1, "j2": res2}
    MetricsCalculator.calculate_metrics(summary, results, machines={}, now=2.0)

    # Expected: (2 * 0.90 + 6 * 0.80) / (2 + 6) = (1.80 + 4.80) / 8 = 6.60 / 8 = 0.825
    # (Unweighted would have been (0.90 + 0.80) / 2 = 0.850)
    assert pytest.approx(summary.average_fidelity, rel=1e-5) == 0.825
    assert summary.succeeded_jobs == 2
    assert summary.failed_jobs == 0


def test_actual_waiting_time_with_cutting_gaps():
    """Verify average_waiting_time calculates actual queue delays (TAT - execution_time)."""
    summary = ExecutionSummary()

    # Job 1: Arrived at 0.0, ran [0.0, 2.0], duration 2.0 -> Waiting = 0.0
    job1 = JobInfo(job_name="j1", arrival_time=0.0)
    res1 = ExecutionResult(job_info=job1, status="SUCCEEDED", start_time=0.0, end_time=2.0, execution_time=2.0)

    # Job 2: Arrived at 0.0, start 0.0, completed at 5.0, but total active execution was only 3.0
    # (e.g. cut subcircuit A ran [0.0, 1.0], subcircuit B waited until [3.0, 5.0])
    # TAT = 5.0 - 0.0 = 5.0, T_exec = 3.0 -> Waiting time = 5.0 - 3.0 = 2.0
    job2 = JobInfo(job_name="j2", arrival_time=0.0)
    res2 = ExecutionResult(job_info=job2, status="SUCCEEDED", start_time=0.0, end_time=5.0, execution_time=3.0)

    results = {"j1": res1, "j2": res2}
    MetricsCalculator.calculate_metrics(summary, results, machines={}, now=5.0)

    # Average Turnaround: (2.0 + 5.0) / 2 = 3.5
    assert summary.average_turnaround_time == 3.5
    # Average Waiting: (0.0 + 2.0) / 2 = 1.0
    assert summary.average_waiting_time == 1.0


def test_cluster_and_machine_qubit_utilization():
    """Verify qubit space-time utilization on individual machines and cluster-wide."""
    summary = ExecutionSummary()

    @dataclass
    class MockMachine:
        name: str
        capacity: int

    machines = {
        "m1": MockMachine(name="m1", capacity=5),
        "m2": MockMachine(name="m2", capacity=5),
    }

    # Batch 1 on m1: runs [0.0, 4.0] using 3 logical qubits -> qubit_time = 3 * 4 = 12
    summary.batches.append(
        BatchExecutionRecord(
            batch_id=1, machine_name="m1", job_ids=("j1",), shots=1000,
            start_time=0.0, end_time=4.0, logical_qubits=3, status="SUCCEEDED"
        )
    )
    # Batch 2 on m2: runs [0.0, 2.0] using 2 logical qubits -> qubit_time = 2 * 2 = 4
    summary.batches.append(
        BatchExecutionRecord(
            batch_id=2, machine_name="m2", job_ids=("j2",), shots=1000,
            start_time=0.0, end_time=2.0, logical_qubits=2, status="SUCCEEDED"
        )
    )

    MetricsCalculator.calculate_metrics(summary, results={}, machines=machines, now=4.0)

    # Makespan = 4.0
    # m1: capacity=5, qubit_time=12, capacity*makespan = 20 -> util = 12/20 = 0.60
    assert pytest.approx(summary.machines["m1"].utilization, rel=1e-5) == 0.60
    # m2: capacity=5, qubit_time=4, capacity*makespan = 20 -> util = 4/20 = 0.20
    assert pytest.approx(summary.machines["m2"].utilization, rel=1e-5) == 0.20

    # Cluster qubit utilization: (12 + 4) / ((5 + 5) * 4.0) = 16 / 40 = 0.40
    assert pytest.approx(summary.cluster_qubit_utilization, rel=1e-5) == 0.40


def test_queue_policy_strict_vs_relaxed_dispatch():
    """Verify strict stops on Head-of-Line blocking, whereas relaxed/backfill skips to fit available capacity."""
    orchestrator = ConcreteExecutionPhase()

    qc_large = QuantumCircuit(5)
    job_large = JobInfo(job_name="large", circuit=qc_large, num_qubits=5, arrival_time=0.0)
    sched_large = SchedulerJobInfo(job_information=job_large, assigned_machine="m1")

    qc_small = QuantumCircuit(2)
    job_small = JobInfo(job_name="small", circuit=qc_small, num_qubits=2, arrival_time=0.0)
    sched_small = SchedulerJobInfo(job_information=job_small, assigned_machine="m1")

    scheduler_job = {"large": sched_large, "small": sched_small}
    results = {
        "large": ExecutionResult(job_info=job_large, status="PENDING"),
        "small": ExecutionResult(job_info=job_small, status="PENDING"),
    }

    # Case 1: Machine capacity is 4. Queue has ["large" (5q), "small" (2q)].
    # Under strict policy: "large" exceeds 4 -> break! "small" is NOT selected.
    queue_strict = ["large", "small"]
    active_strict = orchestrator._select_jobs(
        now=0.0, scheduler_job=scheduler_job, results=results,
        queue=queue_strict, active=[], capacity=4, policy="strict"
    )
    assert active_strict == []
    assert queue_strict == ["large", "small"]

    # Case 2: Under relaxed / backfill policy: "large" exceeds 4 -> continue! "small" (2q <= 4) is selected!
    queue_relaxed = ["large", "small"]
    active_relaxed = orchestrator._select_jobs(
        now=0.0, scheduler_job=scheduler_job, results=results,
        queue=queue_relaxed, active=[], capacity=4, policy="relaxed"
    )
    assert active_relaxed == ["small"]
    assert queue_relaxed == ["large"]
