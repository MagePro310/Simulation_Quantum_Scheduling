"""Domain models for quantum circuit jobs and execution results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qiskit import QuantumCircuit


@dataclass
class JobInfo:
    """Stores quantum circuit job metadata, circuit definition, and cutting context."""

    # Basic information
    job_name: str | None = None
    circuit: QuantumCircuit | None = None
    num_qubits: int | None = None
    shots: int | None = None

    # Scheduling parameters
    arrival_time: float | None = None
    priority: int | None = None

    # Circuit cutting context
    parent_job: JobInfo | None = None
    children_jobs: dict[str, JobInfo] | None = None
    partition_label: str | None = None
    subexperiments: list[QuantumCircuit] | None = None
    cutting_context: Any | None = None
    cutting_overhead: float = 0.0


@dataclass
class SchedulerJobInfo:
    """Stores scheduling assignments and dependencies for a quantum job."""

    job_information: JobInfo | None = None
    assigned_machine: str | None = None
    dispatch_order: int | None = None
    depends_on: list[JobInfo | None] | None = None  # Jobs that must complete before this job


@dataclass
class ExecutionResult:
    """Stores simulation execution results and fidelity metrics for a quantum job."""

    job_info: JobInfo
    assigned_machine: str | None = None
    distribution_no_noise: dict[str, int] | None = None
    distribution_with_noise: dict[str, int] | None = None
    fidelity: float | None = None
    tvd: float | None = None
    uncut_distribution: dict[str, int] | None = None
    reconstructed_distribution: dict[str, int] | None = None
    cutting_overhead: float = 0.0
    start_time: float | None = None
    end_time: float | None = None
    execution_time: float | None = None
    status: str = "PENDING"
    error_reason: str | None = None
    requested_shots: int = 0
    completed_shots: int = 0
