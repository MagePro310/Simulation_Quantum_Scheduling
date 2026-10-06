"""Reconstruction handler: update job results and coordinate circuit cutting reconstruction."""

from collections import Counter

from source.component.dataclass.execution_info import BatchCompletion
from source.component.dataclass.job_info import ExecutionResult, JobInfo
from source.component.help_function.fidelity import (
    compute_hellinger_fidelity,
    compute_total_variation_distance,
)
from source.flow.execution.circuit_reconstructor import CircuitReconstructor


class ReconstructionHandler:
    """Handle batch result updating, fidelity calculation, and parent job reconstruction."""

    def update_job_results(
        self,
        completion: BatchCompletion,
        results: dict[str, ExecutionResult],
    ) -> list[str]:
        """Update results for completed batch and return remaining active job IDs."""
        remaining = []
        record = completion.batch_record

        for job_name in record.job_ids:
            result = results[job_name]
            result.end_time = record.end_time
            result.execution_time += record.end_time - record.start_time

            if completion.error:
                result.status = "FAILED"
                result.error_reason = completion.error
                continue

            # Add measurement counts
            counts = completion.job_counts[job_name]
            result.distribution_no_noise = dict(
                Counter(result.distribution_no_noise) + Counter(counts.distribution_no_noise)
            )
            result.distribution_with_noise = dict(
                Counter(result.distribution_with_noise) + Counter(counts.distribution_with_noise)
            )
            result.completed_shots += record.shots

            # Check if job completed its required shots
            if result.completed_shots >= result.requested_shots:
                result.status = "SUCCEEDED"
                h_fid = compute_hellinger_fidelity(
                    result.distribution_no_noise,
                    result.distribution_with_noise,
                )
                tvd = compute_total_variation_distance(
                    result.distribution_no_noise,
                    result.distribution_with_noise,
                )
                result.fidelity = h_fid
                result.hellinger_fidelity = h_fid
                result.bhattacharyya_fidelity = h_fid
                result.tvd = tvd

                # If this is a cut subcircuit, check if all subcircuits have finished
                info = getattr(result, "job_info", None)
                if info and getattr(info, "parentJob", None) and getattr(info.parentJob, "cutting_context", None):
                    parent_job = info.parentJob
                    ctx = parent_job.cutting_context
                    child_results = [
                        r for r in results.values()
                        if r.job_info and getattr(r.job_info, "parentJob", None) is parent_job
                    ]
                    all_done = (
                        len(child_results) == len(ctx.subcircuits)
                        and all(r.status == "SUCCEEDED" for r in child_results)
                        and all(label in ctx.sub_results for label in ctx.subcircuits.keys())
                    )
                    if all_done and not getattr(ctx, "reconstructed", False):
                        ctx.reconstructed = True
                        self.reconstruct_parent_job(parent_job, results)
            else:
                result.status = "RUNNING"
                remaining.append(job_name)

        return remaining

    @staticmethod
    def reconstruct_parent_job(parent_job: JobInfo, results: dict[str, ExecutionResult]) -> None:
        """Reconstruct parent job output distribution and evaluate fidelity."""
        parent_name = parent_job.job_name or "parent_job"
        ctx = parent_job.cutting_context
        shots = parent_job.shots or 1024

        try:
            uncut_counts, recon_counts, fidelity, tvd, _ = CircuitReconstructor.reconstruct_distribution(
                ctx, shots=shots
            )

            # Store in parent execution result
            child_results = [
                r for r in results.values()
                if r.job_info and getattr(r.job_info, "parentJob", None) is parent_job
            ]
            p_start = min((r.start_time for r in child_results if r.start_time is not None), default=0.0)
            p_end = max((r.end_time for r in child_results if r.end_time is not None), default=0.0)
            p_duration = sum(r.execution_time for r in child_results if r.execution_time is not None)
            overhead = getattr(parent_job, "cutting_overhead", 0.0)

            results[parent_name] = ExecutionResult(
                job_info=parent_job,
                assigned_machine="cut_reconstruction",
                distribution_no_noise=recon_counts,
                distribution_with_noise=recon_counts,
                execution_time=p_duration,
                start_time=p_start,
                end_time=p_end,
                requested_shots=shots,
                completed_shots=shots,
                fidelity=fidelity,
                hellinger_fidelity=fidelity,
                status="SUCCEEDED",
                tvd=tvd,
                bhattacharyya_fidelity=fidelity,
                uncut_distribution=uncut_counts,
                reconstructed_distribution=recon_counts,
                cutting_overhead=overhead,
            )
        except Exception as e:
            print(f"│ Circuit reconstruction failed for {parent_name}: {e}")
            results[parent_name] = ExecutionResult(
                job_info=parent_job,
                assigned_machine="cut_reconstruction",
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=0.0,
                start_time=0.0,
                end_time=0.0,
                requested_shots=shots,
                completed_shots=0,
                fidelity=0.0,
                hellinger_fidelity=0.0,
                status="FAILED",
                error_reason=f"Circuit reconstruction failed: {e}",
                cutting_overhead=getattr(parent_job, "cutting_overhead", 0.0),
            )

