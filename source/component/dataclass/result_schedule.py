"""Input/scheduling metadata and a reference to the execution report."""

from dataclasses import dataclass

from source.component.dataclass.execution_info import ExecutionSummary


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
