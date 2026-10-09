"""Timeline reporter: separated presentation and logging layer for quantum execution.

Decouples console reporting from the discrete-event simulation engine, keeping
orchestrator and batch executors focused purely on scheduling logic.
"""

from typing import Any
from source.component.dataclass.job_info import ExecutionResult


class ConsoleTimelineReporter:
    """Standard console timeline reporter providing human-readable formatted cards."""

    def print_start(self) -> None:
        """Print execution start banner."""
        print("\n=== Quantum Execution Started ===")

    def print_timeline_status(
        self,
        now: float,
        results: dict[str, ExecutionResult],
        machine_states: dict[str, Any],
    ) -> None:
        """Print current execution timeline status card."""
        if not any(r.status in {"PENDING", "RUNNING"} for r in results.values()):
            return

        print(f"\n┌─ Time: {now:.3f}s ─────────────────────────────────────")
        if pending := [name for name, r in results.items() if r.status == "PENDING"]:
            print(f"│ Queue    : {', '.join(pending)}")

        for machine_name, state in machine_states.items():
            if state.busy and state.active:
                print(f"│ Running  : {machine_name:<15} → {', '.join(state.active)}")

        print("└" + "─" * 50)

    def print_dispatch(
        self,
        machine_name: str,
        job_ids: tuple[str, ...],
        shots: int,
        is_cut: bool = False,
    ) -> None:
        """Print batch dispatch notice."""
        cut_suffix = " (cut subcircuits)" if is_cut else ""
        print(f"│ Dispatch : {machine_name:<15} → {', '.join(job_ids)} ({shots} shots{cut_suffix})")

    def print_completion(
        self,
        job_name: str,
        execution_time: float,
        fidelity: Any,
    ) -> None:
        """Print job completion notice with duration and fidelity."""
        fid_str = f"{fidelity:.4f}" if isinstance(fidelity, (int, float)) else "subcircuit"
        print(f"│ Complete : {job_name:<15} (duration: {execution_time:.3f}s, fidelity: {fid_str})")


class SilentTimelineReporter:
    """Silent reporter that suppresses console output (ideal for high-throughput batch benchmarks)."""

    def print_start(self) -> None:
        pass

    def print_timeline_status(
        self,
        now: float,
        results: dict[str, ExecutionResult],
        machine_states: dict[str, Any],
    ) -> None:
        pass

    def print_dispatch(
        self,
        machine_name: str,
        job_ids: tuple[str, ...],
        shots: int,
        is_cut: bool = False,
    ) -> None:
        pass

    def print_completion(
        self,
        job_name: str,
        execution_time: float,
        fidelity: Any,
    ) -> None:
        pass

