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


@dataclass
class MachineExecutionResult:
    machine_name: str
    utilization: float = 0.0
    busy_time: float = 0.0
    qubit_time: float = 0.0


@dataclass
class ExecutionSummary:
    """Single owner of realized execution metrics, machine reports, and batches.

    Virtual times are seconds. Timing averages and fidelity include successful
    jobs only; throughput divides successes by the full makespan. Waiting time
    includes gaps between a job's batches. Utilization measures logical qubit
    allocation over capacity times the full makespan, including idle intervals.
    Scheduling wall time is recorded separately in ResultOfSchedule.
    """

    makespan: float = 0.0
    total_turnaround_time: float = 0.0
    total_waiting_time: float = 0.0
    total_response_time: float = 0.0
    average_turnaround_time: float = 0.0
    average_waiting_time: float = 0.0
    average_response_time: float = 0.0
    job_completion_rate: float = 0.0
    average_fidelity: float = 0.0
    succeeded_jobs: int = 0
    failed_jobs: int = 0
    blocked_jobs: int = 0
    machines: dict[str, MachineExecutionResult] = field(default_factory=dict)
    batches: list[BatchExecutionRecord] = field(default_factory=list)
