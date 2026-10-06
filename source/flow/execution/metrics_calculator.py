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
            # 1. Average Turnaround Time
            summary.average_turnaround_time = sum(
                r.end_time - (r.job_info.arrival_time or 0) for r in succeeded
            ) / len(succeeded)

            # 2. Average Waiting Time (Turnaround time minus active execution time)
            waiting_times = [
                max(
                    0.0,
                    (r.end_time - (r.job_info.arrival_time or 0)) - (r.execution_time if r.execution_time is not None else (r.end_time - r.start_time))
                )
                for r in succeeded
            ]
            summary.average_waiting_time = sum(waiting_times) / len(succeeded)

            # 3. Average Fidelity (Qubit-weighted across succeeded jobs)
            weighted_fid_sum = 0.0
            total_qubits = 0
            for r in succeeded:
                if r.fidelity is not None:
                    q = (
                        r.job_info.circuit.num_qubits
                        if (r.job_info and getattr(r.job_info, "circuit", None))
                        else (getattr(r.job_info, "num_qubits", 1) or 1)
                    )
                    weighted_fid_sum += q * r.fidelity
                    total_qubits += q
            summary.average_fidelity = (weighted_fid_sum / total_qubits) if total_qubits > 0 else 0.0

        # 4. Machine and Cluster Qubit Space-Time Utilization
        total_qubit_time = 0.0
        total_cluster_capacity = sum(getattr(m, "capacity", 0) for m in machines.values())

        for machine_name in machines:
            machine_obj = machines[machine_name]
            cap = getattr(machine_obj, "capacity", 1) or 1
            batches = [b for b in summary.batches if b.machine_name == machine_name and b.status == "SUCCEEDED"]
            busy_time = sum(b.end_time - b.start_time for b in batches)
            qubit_time = sum(b.logical_qubits * (b.end_time - b.start_time) for b in batches)
            total_qubit_time += qubit_time

            summary.machines[machine_name] = MachineExecutionResult(
                machine_name=machine_name,
                busy_time=busy_time,
                qubit_time=qubit_time,
                utilization=qubit_time / (cap * summary.makespan) if (summary.makespan > 0 and cap > 0) else 0.0,
            )

        if summary.makespan > 0 and total_cluster_capacity > 0:
            summary.cluster_qubit_utilization = total_qubit_time / (total_cluster_capacity * summary.makespan)

    @staticmethod
    def print_summary(summary: ExecutionSummary):
        """Print execution summary."""
        overhead_str = f"; total cutting overhead {summary.total_cutting_overhead:g}" if summary.total_cutting_overhead > 0 else ""
        print(
            f"\nExecution completed: {summary.succeeded_jobs} succeeded, "
            f"{summary.failed_jobs} failed, "
            f"{summary.blocked_jobs} blocked; "
            f"virtual makespan {summary.makespan:.6g}s; "
            f"avg turnaround {summary.average_turnaround_time:.6g}s; "
            f"avg waiting {summary.average_waiting_time:.6g}s; "
            f"avg fidelity (qubit-wt) {summary.average_fidelity:.4f}; "
            f"cluster qubit util {summary.cluster_qubit_utilization * 100:.2f}%"
            f"{overhead_str}"
        )
