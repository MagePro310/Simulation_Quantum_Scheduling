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
    execution_summary: ExecutionSummary | None = None

    def capture_execution(self, summary: ExecutionSummary) -> None:
        """Attach the execution report without copying its metric values."""
        self.execution_summary = summary
