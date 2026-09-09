"""Result handler: complete batches and update job results."""

from collections import Counter

from source.component.dataclass.execution_info import BatchCounts
from source.component.dataclass.job_info import ExecutionResult


class ResultHandler:
    """Handle batch completion and update job results."""

    @staticmethod
    def complete_batch(completion, results: dict[str, ExecutionResult], print_completion: bool = True) -> list[str]:
        """Complete batch and update job results.

        Returns:
            List of remaining active jobs
        """
        record = completion.record
        record.status = "FAILED" if completion.error else "SUCCEEDED"
        record.error_reason = completion.error

        remaining = []
        for name in record.job_ids:
            result = results[name]
            result.end_time = record.end_time
            result.execution_time += record.end_time - record.start_time

            if completion.error:
                result.status = "FAILED"
                result.error_reason = completion.error
                continue

            # Accumulate counts
            counts = completion.counts[name]
            result.distribution_no_noise = dict(
                Counter(result.distribution_no_noise) + Counter(counts.distribution_no_noise)
            )
            result.distribution_with_noise = dict(
                Counter(result.distribution_with_noise) + Counter(counts.distribution_with_noise)
            )
            result.completed_shots += record.shots

            # Check completion
            if ResultHandler._is_job_complete(result):
                result.status = "SUCCEEDED"
                # Calculate fidelity
                all_keys = set(result.distribution_no_noise) | set(result.distribution_with_noise)
                overlap = sum(
                    min(result.distribution_no_noise.get(k, 0), result.distribution_with_noise.get(k, 0))
                    for k in all_keys
                )
                result.fidelity = overlap / result.completed_shots if result.completed_shots else 1.0
                if print_completion:
                    print(f"│ Complete : {name:<15} (duration: {result.execution_time:.3f}s, fidelity: {result.fidelity:.4f})")
            else:
                result.status = "RUNNING"
                remaining.append(name)

        return remaining

    @staticmethod
    def _is_job_complete(result: ExecutionResult) -> bool:
        """Check if job has completed all shots."""
        return result.completed_shots >= result.requested_shots

    @staticmethod
    def block_dependents(scheduler_job, results):
        """Propagate failure status to dependent jobs."""
        changed = True
        while changed:
            changed = False
            for name, job in scheduler_job.items():
                if results[name].status != "PENDING":
                    continue

                failed = []
                for dep_info in job.depends_on:
                    for dep_name, dep_job in scheduler_job.items():
                        if dep_job.job_information is dep_info:
                            if results[dep_name].status in {"FAILED", "BLOCKED"}:
                                failed.append(dep_name)
                            break

                if failed:
                    results[name].status = "BLOCKED"
                    results[name].error_reason = f"Dependencies failed or blocked: {failed}"
                    changed = True
