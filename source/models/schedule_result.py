"""Models capturing scheduling metadata and simulation execution summaries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MachineExecutionResult:
    """Telemetry and utilization metrics for an individual quantum machine."""

    machine_name: str
    utilization: float = 0.0
    busy_time: float = 0.0
    qubit_time: float = 0.0


@dataclass
class ExecutionSummary:
    """Realized execution metrics, machine reports, and batch history.

    Virtual times are in seconds:
    - makespan: total virtual execution makespan
    - average_turnaround_time: mean (completion - arrival) across succeeded jobs
    - average_waiting_time: mean actual waiting time in queue
    - average_fidelity: qubit-weighted mean circuit fidelity across succeeded jobs
    - cluster_qubit_utilization: total qubit space-time over (capacity * makespan)
    - total_cutting_overhead: sum of sampling overhead gamma^2 from circuit cutting
    """

    makespan: float = 0.0
    average_turnaround_time: float = 0.0
    average_waiting_time: float = 0.0
    average_fidelity: float = 0.0
    cluster_qubit_utilization: float = 0.0
    total_cutting_overhead: float = 0.0
    succeeded_jobs: int = 0
    failed_jobs: int = 0
    blocked_jobs: int = 0
    machines: dict[str, MachineExecutionResult] = field(default_factory=dict)
    batches: list = field(default_factory=list)


@dataclass
class ResultOfSchedule:
    """Capture phase metadata and reference to realization execution summary."""

    num_circuits: int = 0
    name_circuits: str = ""
    average_qubits: float = 0.0
    name_machines: list[str] = field(default_factory=list)
    name_schedule: str = ""
    schedule_latency: float = 0.0
    exceed_cutting_policy: str = "greedy"
    optional_cutting: bool = False
    optional_cutting_policy: str | None = None
    queue_policy: str = "strict"
    seed: int = 0
    workload_fingerprint: str = ""
    git_commit: str = ""
    config: dict = field(default_factory=dict)
    execution_summary: ExecutionSummary | None = None

    def capture_execution(self, summary: ExecutionSummary) -> None:
        """Attach the execution report to this schedule result."""
        self.execution_summary = summary
