"""Reconstruction handler: update job results, merge shot shards, and reconstruct cut circuits."""

from source.models.execution import BatchCompletion
from source.models.job import ExecutionResult, JobInfo
from source.utils.fidelity import (
    compute_hellinger_fidelity,
    compute_total_variation_distance,
)
from source.flow.execution.circuit_reconstructor import CircuitReconstructor
from source.flow.execution.shot_merger import (
    SHOT_MERGE_MACHINE,
    build_logical_result,
    merge_counts,
    merge_primitive_results,
    merged_busy_time,
    shard_results_of,
)


def _leaf_results(child_results: list[ExecutionResult], results: dict[str, ExecutionResult]) -> list[ExecutionResult]:
    """Replace each child that was split into shot shards by its shards' results.

    Busy time is measured on what actually ran, so a subcircuit whose shards ran
    with a gap between them does not count the gap as busy time.
    """
    leaves: list[ExecutionResult] = []
    for result in child_results:
        shards = shard_results_of(result.job_info, results) if result.job_info and result.job_info.shot_shards else []
        leaves.extend(shards or [result])
    return leaves


class ReconstructionHandler:
    """Handle batch result updating, shot shard merging, fidelity, and parent job reconstruction."""

    def update_job_results(
        self,
        completion: BatchCompletion,
        results: dict[str, ExecutionResult],
        seed: int = 0,
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

            # Accumulate measurement counts and, for cut subcircuits, the QPD results
            counts = completion.job_counts[job_name]
            result.distribution_no_noise = merge_counts(result.distribution_no_noise, counts.distribution_no_noise)
            result.distribution_with_noise = merge_counts(result.distribution_with_noise, counts.distribution_with_noise)
            result.sub_result = merge_primitive_results([result.sub_result, counts.sub_result])
            result.completed_shots += record.shots

            # Check if job completed its required shots
            if result.completed_shots >= result.requested_shots:
                result.status = "SUCCEEDED"
                result.fidelity = compute_hellinger_fidelity(
                    result.distribution_no_noise,
                    result.distribution_with_noise,
                )
                result.tvd = compute_total_variation_distance(
                    result.distribution_no_noise,
                    result.distribution_with_noise,
                )
                self._on_job_succeeded(result, results, seed=seed)
            else:
                result.status = "RUNNING"
                remaining.append(job_name)

        return remaining

    def _on_job_succeeded(
        self,
        result: ExecutionResult,
        results: dict[str, ExecutionResult],
        seed: int = 0,
    ) -> None:
        """Propagate a finished job: merge shot shards, then reconstruct cut parents."""
        info = result.job_info
        if info is None:
            return

        # A shot shard: once every shard is done, the logical job gets a merged result
        if info.shot_parent is not None:
            self._merge_shards_if_done(info.shot_parent, results, seed=seed)
            return

        # A cut subcircuit: record its QPD results, then reconstruct once all are in
        parent_job = info.parent_job
        ctx = getattr(parent_job, "cutting_context", None) if parent_job else None
        if ctx is None:
            return

        if result.sub_result is not None:
            ctx.sub_results[info.partition_label] = result.sub_result

        child_results = [
            r for r in results.values()
            if r.job_info and getattr(r.job_info, "parent_job", None) is parent_job
        ]
        all_done = (
            len(child_results) == len(ctx.subcircuits)
            and all(r.status == "SUCCEEDED" for r in child_results)
            and all(label in ctx.sub_results for label in ctx.subcircuits.keys())
        )
        if all_done and not getattr(ctx, "reconstructed", False):
            ctx.reconstructed = True
            self.reconstruct_parent_job(parent_job, results, seed=seed)

    def _merge_shards_if_done(
        self,
        logical_job: JobInfo,
        results: dict[str, ExecutionResult],
        seed: int = 0,
    ) -> None:
        """Merge a logical job's shards into one result when all of them have succeeded."""
        logical_name = logical_job.job_name
        if logical_name in results:
            return

        shards = shard_results_of(logical_job, results)
        if len(shards) != len(logical_job.shot_shards or {}) or any(r.status != "SUCCEEDED" for r in shards):
            return

        merged = build_logical_result(logical_job, shards)
        results[logical_name] = merged
        self._on_job_succeeded(merged, results, seed=seed)

    @staticmethod
    def reconstruct_parent_job(
        parent_job: JobInfo,
        results: dict[str, ExecutionResult],
        seed: int = 0,
    ) -> None:
        """Reconstruct parent job output distribution and evaluate fidelity."""
        parent_name = parent_job.job_name or "parent_job"
        ctx = parent_job.cutting_context
        shots = parent_job.shots or 1024

        try:
            uncut_counts, recon_counts, fidelity, tvd, _ = CircuitReconstructor.reconstruct_distribution(
                ctx, shots=shots, seed=seed
            )

            # Store in parent execution result
            child_results = [
                r for r in results.values()
                if r.job_info and getattr(r.job_info, "parent_job", None) is parent_job
            ]
            p_start = min((r.start_time for r in child_results if r.start_time is not None), default=0.0)
            p_end = max((r.end_time for r in child_results if r.end_time is not None), default=0.0)
            p_duration = merged_busy_time(_leaf_results(child_results, results))
            overhead = getattr(parent_job, "cutting_overhead", 0.0)

            results[parent_name] = ExecutionResult(
                job_info=parent_job,
                assigned_machine="cut_reconstruction",
                distribution_no_noise=uncut_counts,  # exact ideal, as for uncut jobs
                distribution_with_noise=recon_counts,
                execution_time=p_duration,
                start_time=p_start,
                end_time=p_end,
                requested_shots=shots,
                completed_shots=shots,
                fidelity=fidelity,
                status="SUCCEEDED",
                tvd=tvd,
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
                status="FAILED",
                error_reason=f"Circuit reconstruction failed: {e}",
                cutting_overhead=getattr(parent_job, "cutting_overhead", 0.0),
            )

    @staticmethod
    def finalize_unmerged_shards(results: dict[str, ExecutionResult]) -> None:
        """Give jobs whose shot shards did not all succeed a result of their own.

        Run this before finalize_unreconstructed_parents: a cut subcircuit split into
        shards needs its own result before its parent can be finalized.
        """
        logical_jobs: dict[int, JobInfo] = {}
        for result in list(results.values()):
            shot_parent = getattr(result.job_info, "shot_parent", None)
            if shot_parent is not None:
                logical_jobs[id(shot_parent)] = shot_parent

        for logical_job in logical_jobs.values():
            logical_name = logical_job.job_name
            if logical_name in results:
                continue

            shards = shard_results_of(logical_job, results)
            status = "FAILED" if any(r.status == "FAILED" for r in shards) else "BLOCKED"
            reasons = sorted({r.error_reason for r in shards if r.error_reason})
            starts = [r.start_time for r in shards if r.start_time is not None]
            ends = [r.end_time for r in shards if r.end_time is not None]
            results[logical_name] = ExecutionResult(
                job_info=logical_job,
                assigned_machine=SHOT_MERGE_MACHINE,
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=merged_busy_time(shards),
                start_time=min(starts, default=None),
                end_time=max(ends, default=None),
                requested_shots=logical_job.shots or 1024,
                completed_shots=sum(r.completed_shots for r in shards if r.status == "SUCCEEDED"),
                status=status,
                error_reason="; ".join(reasons) or f"Shot shard {status.lower()}",
                cutting_overhead=logical_job.cutting_overhead,
            )

    @staticmethod
    def finalize_unreconstructed_parents(results: dict[str, ExecutionResult]) -> None:
        """Give cut jobs with a failed or blocked subcircuit a result of their own.

        Metrics count only parent-level jobs, so without this a cut job that never
        reconstructed would be missing from the succeeded/failed/blocked totals.
        """
        children_by_parent: dict[int, list[ExecutionResult]] = {}
        parents: dict[int, JobInfo] = {}
        for result in results.values():
            parent_job = getattr(result.job_info, "parent_job", None)
            if parent_job is not None:
                parents[id(parent_job)] = parent_job
                children_by_parent.setdefault(id(parent_job), []).append(result)

        for key, parent_job in parents.items():
            parent_name = parent_job.job_name or "parent_job"
            if parent_name in results:
                continue

            children = children_by_parent[key]
            status = "FAILED" if any(r.status == "FAILED" for r in children) else "BLOCKED"
            reasons = sorted({r.error_reason for r in children if r.error_reason})
            starts = [r.start_time for r in children if r.start_time is not None]
            ends = [r.end_time for r in children if r.end_time is not None]
            results[parent_name] = ExecutionResult(
                job_info=parent_job,
                assigned_machine="cut_reconstruction",
                distribution_no_noise={},
                distribution_with_noise={},
                execution_time=merged_busy_time(_leaf_results(children, results)),
                start_time=min(starts, default=None),
                end_time=max(ends, default=None),
                requested_shots=parent_job.shots or 1024,
                status=status,
                error_reason="; ".join(reasons) or f"Subcircuit {status.lower()}",
                cutting_overhead=parent_job.cutting_overhead,
            )
