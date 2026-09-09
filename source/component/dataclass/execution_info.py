"""Batch contracts and reports shared by the execution phase helpers."""

from dataclasses import dataclass, field

from qiskit import QuantumCircuit


@dataclass
class PreparedBatch:
    job_ids: tuple[str, ...]
    merged_circuit: QuantumCircuit
    transpiled_circuit: QuantumCircuit
    classical_bits: dict[str, tuple[int, ...]]
    logical_qubits: int
    duration_per_shot: float


@dataclass
class BatchCounts:
    distribution_no_noise: dict[str, int]
    distribution_with_noise: dict[str, int]


@dataclass
class BatchExecutionRecord:
    batch_id: int
    machine_name: str
    job_ids: tuple[str, ...]
    shots: int
    start_time: float
    end_time: float
    logical_qubits: int
    status: str = "RUNNING"
    error_reason: str | None = None


