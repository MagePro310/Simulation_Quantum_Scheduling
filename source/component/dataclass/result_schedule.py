"""Input/scheduling metadata and a reference to the execution report."""

from dataclasses import dataclass, field


@dataclass
class MachineExecutionResult:
    machine_name: str
    utilization: float = 0.0
    busy_time: float = 0.0
    qubit_time: float = 0.0


@dataclass
class ExecutionSummary:
    """Single owner of realized execution metrics, machine reports, and batches.

    Virtual times are seconds. Core metrics are non-subsumed and orthogonal:
    - makespan: total virtual execution makespan
    - average_turnaround_time: mean (completion - arrival) across succeeded jobs
    - average_waiting_time: mean actual waiting time in queue (TAT - active execution)
    - average_fidelity: qubit-weighted mean circuit fidelity across succeeded jobs
    - cluster_qubit_utilization: total qubit-time over total cluster capacity × makespan
    - total_cutting_overhead: sum of sampling overhead gamma^2 from circuit cutting
    """

    makespan: float = 0.0
    average_turnaround_time: float = 0.0
    average_waiting_time: float = 0.0
    average_fidelity: float = 0.0  # Qubit-weighted average fidelity
    cluster_qubit_utilization: float = 0.0
    total_cutting_overhead: float = 0.0
    succeeded_jobs: int = 0
    failed_jobs: int = 0
    blocked_jobs: int = 0
    machines: dict[str, MachineExecutionResult] = field(default_factory=dict)
    batches: list = field(default_factory=list)


@dataclass
class ResultOfSchedule:
    """Capture phase metadata; execution_summary owns all execution metrics."""

    numCircuits: int = 0
    nameCircuits: str = ""
    averageQubits: float = 0.0
    nameMachines: str | list[str] = ""
    nameSchedule: str = ""
    ScheduleLatency: float = 0.0
    exceed_cutting_policy: str = "greedy"
    optional_cutting: bool = False
    optional_cutting_policy: str | None = None
    queue_policy: str = "strict"
    seed: int = 0
    execution_summary: ExecutionSummary | None = None


    def capture_execution(self, summary: ExecutionSummary) -> None:
        """Attach the execution report without copying its metric values."""
        self.execution_summary = summary
