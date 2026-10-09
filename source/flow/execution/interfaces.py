"""Execution layer protocols and strategy contracts (PEP 8 compliant, no 'I' prefix).

This module defines the architectural contracts for all pluggable execution components,
allowing custom dispatchers, layout strategies, and reporters to be injected freely.
"""

from typing import Any, Protocol
from source.component.dataclass.job_info import ExecutionResult, SchedulerJobInfo


class JobDispatcherProtocol(Protocol):
    """Protocol for job queue candidate selection and dependency cascade checking."""

    def select_jobs(
        self,
        now: float,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
        queue: list[str],
        active: list[str],
        capacity: int,
        policy: str,
    ) -> list[str]:
        """Select eligible jobs from machine queue that can run at current simulation time."""
        ...

    def block_failed_dependents(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        results: dict[str, ExecutionResult],
    ) -> None:
        """Mark jobs as BLOCKED if their dependencies failed or were blocked."""
        ...


class LayoutStrategy(Protocol):
    """Extensibility hook for physical qubit layout assignment on quantum backends.

    Allows future algorithms (e.g. crosstalk-mitigating, subgraph partitioning)
    to specify physical qubit placements for composite batches.
    """

    def get_initial_layout(
        self,
        backend: Any,
        jobs: dict[str, Any],
    ) -> list[int] | dict[Any, int] | None:
        """Calculate and return physical qubit mapping or None for default Qiskit heuristic."""
        ...


class DefaultLayoutStrategy:
    """Default layout strategy: returns None so Qiskit Pass Manager runs its native heuristic (Sabre/VF2)."""

    def get_initial_layout(
        self,
        backend: Any,
        jobs: dict[str, Any],
    ) -> None:
        """Return None to delegate layout selection to Qiskit's pass manager."""
        return None


class TimelineReporterProtocol(Protocol):
    """Protocol for execution status reporting, console logging, and event tracing."""

    def print_start(self) -> None:
        """Report execution start."""
        ...

    def print_timeline_status(
        self,
        now: float,
        results: dict[str, ExecutionResult],
        machine_states: dict[str, Any],
    ) -> None:
        """Print current timeline status card."""
        ...

    def print_dispatch(
        self,
        machine_name: str,
        job_ids: tuple[str, ...],
        shots: int,
        is_cut: bool = False,
    ) -> None:
        """Print batch dispatch information."""
        ...

    def print_completion(
        self,
        job_name: str,
        execution_time: float,
        fidelity: Any,
    ) -> None:
        """Print completed job summary."""
        ...

