"""Metrics calculator: calculate execution metrics and summaries."""

from source.component.dataclass.result_schedule import ExecutionSummary, MachineExecutionResult
from source.component.dataclass.job_info import ExecutionResult


class MetricsCalculator:
    """Calculate execution metrics and summaries."""

    @staticmethod
    def calculate_metrics(
        summary: ExecutionSummary,
        results: dict[str, ExecutionResult],
        machines: dict,
        now: float,
    ):
        """Calculate final execution metrics."""
        summary.makespan = now

        # Count job statuses (filter out internal cut subcircuits, keep actual user jobs)
        target_results = {
            k: r for k, r in results.items()
            if getattr(r.job_info, "parentJob", None) is None
        }

        summary.succeeded_jobs = sum(1 for r in target_results.values() if r.status == "SUCCEEDED")
        summary.failed_jobs = sum(1 for r in target_results.values() if r.status == "FAILED")
        summary.blocked_jobs = sum(1 for r in target_results.values() if r.status == "BLOCKED")

        # Total cutting overhead from all cut circuits
        summary.total_cutting_overhead = sum(
            getattr(r, "cutting_overhead", 0.0) or (getattr(r.job_info, "cutting_overhead", 0.0) if r.job_info else 0.0)
            for r in target_results.values()
        )

        # Calculate metrics for succeeded jobs
        succeeded = [r for r in target_results.values() if r.status == "SUCCEEDED" and r.start_time is not None and r.end_time is not None]
        if succeeded:
            summary.total_turnaround_time = sum(r.end_time - (r.job_info.arrival_time or 0) for r in succeeded)
            summary.average_turnaround_time = summary.total_turnaround_time / len(succeeded)
            summary.total_waiting_time = sum(r.start_time - (r.job_info.arrival_time or 0) for r in succeeded)
            summary.average_waiting_time = summary.total_waiting_time / len(succeeded)
            summary.total_response_time = summary.total_waiting_time
            summary.average_response_time = summary.average_waiting_time

            if summary.makespan > 0:
                summary.job_completion_rate = len(succeeded) / summary.makespan

            # Calculate average fidelity
            fidelities = [r.fidelity for r in succeeded if r.fidelity is not None]
            summary.average_fidelity = sum(fidelities) / len(fidelities) if fidelities else 0

        # Machine utilization
        for machine_name in machines:
            batches = [b for b in summary.batches if b.machine_name == machine_name and b.status == "SUCCEEDED"]
            busy_time = sum(b.end_time - b.start_time for b in batches)
            qubit_time = sum(b.logical_qubits * (b.end_time - b.start_time) for b in batches)

            summary.machines[machine_name] = MachineExecutionResult(
                machine_name=machine_name,
                busy_time=busy_time,
                qubit_time=qubit_time,
                utilization=busy_time / summary.makespan if summary.makespan else 0,
            )

    @staticmethod
    def print_summary(summary: ExecutionSummary):
        """Print execution summary."""
        overhead_str = f"; total cutting overhead {summary.total_cutting_overhead:g}" if summary.total_cutting_overhead > 0 else ""
        print(
            f"\nExecution completed: {summary.succeeded_jobs} succeeded, "
            f"{summary.failed_jobs} failed, "
            f"{summary.blocked_jobs} blocked; "
            f"virtual makespan {summary.makespan:.6g} seconds"
            f"{overhead_str}"
        )
