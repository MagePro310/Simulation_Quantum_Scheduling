"""Execution contracts and batch records shared across simulation phases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    sub_result: Any | None = None  # QPD PrimitiveResult for a cut subcircuit


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
    # Logical qubit-seconds actually occupied. None means every qubit of the batch was
    # busy for its whole duration (logical_qubits * duration). A joint cutting batch sets
    # it from its individual circuits, since an uncut job runs in only the first of them.
    qubit_time: float | None = None

    @property
    def occupied_qubit_time(self) -> float:
        """Logical qubit-seconds this batch kept busy."""
        if self.qubit_time is not None:
            return self.qubit_time
        return self.logical_qubits * (self.end_time - self.start_time)


@dataclass
class BatchCompletion:
    """Event triggered when a batch finishes running on a simulator backend."""

    batch_record: BatchExecutionRecord
    job_counts: dict[str, BatchCounts] | None
    error: str | None
