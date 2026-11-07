"""Execution contracts and batch records shared across simulation phases."""

from __future__ import annotations

from dataclasses import dataclass
from qiskit import QuantumCircuit


@dataclass
class PreparedBatch:
    """Pre-transpiled and merged batch of quantum circuits packed on a machine."""

    job_ids: tuple[str, ...]
    merged_circuit: QuantumCircuit
    transpiled_circuit: QuantumCircuit
    classical_bits: dict[str, tuple[int, ...]]
    logical_qubits: int
    duration_per_shot: float


@dataclass
class BatchCounts:
    """Measurement outcome counts for ideal and noisy simulations."""

    distribution_no_noise: dict[str, int]
    distribution_with_noise: dict[str, int]


@dataclass
class BatchExecutionRecord:
    """Execution telemetry record for a single batch run on a quantum machine."""

    batch_id: int
    machine_name: str
    job_ids: tuple[str, ...]
    shots: int
    start_time: float
    end_time: float
    logical_qubits: int
    status: str = "RUNNING"
    error_reason: str | None = None


@dataclass
class BatchCompletion:
    """Event triggered when a batch finishes running on a simulator backend."""

    batch_record: BatchExecutionRecord
    job_counts: dict[str, BatchCounts] | None
    error: str | None
