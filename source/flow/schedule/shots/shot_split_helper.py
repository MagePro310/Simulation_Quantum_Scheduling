"""Helper for distributing one job's shots across several machines.

A job split this way is replaced by shard jobs. Each shard runs the same circuit
(or the same cut subexperiments) with part of the shots, and can be assigned to a
different machine. When every shard succeeds, the execution engine merges their
results back under the original job's name; for a cut subcircuit, that merged
result then feeds circuit reconstruction as usual.

Cut first, then distribute shots: shards cannot be cut, and a shard cannot be
split again.
"""

from dataclasses import replace
from typing import Dict, List

from source.models.job import JobInfo, SchedulerJobInfo


class ShotDistributionHelper:
    """Split a job into shot shards and keep scheduling metadata consistent."""

    @staticmethod
    def can_split(job: SchedulerJobInfo | JobInfo, min_shots_per_shard: int = 1) -> bool:
        """Check whether a job can be split into at least two shards.

        Root jobs and cut subcircuits are eligible. Shards and jobs that were
        already split are not.
        """
        job_info = job.job_information if isinstance(job, SchedulerJobInfo) else job
        if job_info is None or job_info.circuit is None:
            return False
        if job_info.shot_parent is not None or job_info.shot_shards:
            return False
        return (job_info.shots or 0) >= 2 * max(min_shots_per_shard, 1)

    @staticmethod
    def resolve_shares(total_shots: int, shares: List[int] | int) -> List[int]:
        """Turn a shard count or an explicit list of shot counts into a list of shot counts.

        An integer k splits the shots as evenly as possible into k shards, with the
        larger shards first (e.g. 1025 shots into 2 gives [513, 512]).
        """
        if isinstance(shares, int):
            if shares < 2:
                raise ValueError(f"Need at least 2 shards, got {shares}.")
            if shares > total_shots:
                raise ValueError(f"Cannot split {total_shots} shots into {shares} non-empty shards.")
            base, remainder = divmod(total_shots, shares)
            return [base + (1 if i < remainder else 0) for i in range(shares)]

        resolved = [int(s) for s in shares]
        if len(resolved) < 2:
            raise ValueError(f"Need at least 2 shards, got {resolved}.")
        if any(s <= 0 for s in resolved):
            raise ValueError(f"Every shard needs a positive shot count, got {resolved}.")
        if sum(resolved) != total_shots:
            raise ValueError(f"Shard shots {resolved} sum to {sum(resolved)}, expected {total_shots}.")
        return resolved

    @classmethod
    def split_shots(
        cls,
        job: SchedulerJobInfo | JobInfo,
        shares: List[int] | int,
    ) -> Dict[str, SchedulerJobInfo]:
        """Split a job's shots into shard jobs.

        Args:
            job: SchedulerJobInfo or JobInfo to split (a root job or a cut subcircuit).
            shares: Number of equal shards, or explicit shot counts summing to the job's shots.

        Returns:
            Dictionary of {shard_name: SchedulerJobInfo}. Shards are unassigned; the
            caller sets assigned_machine and dispatch_order on each one. They inherit
            the job's dependencies. Return them in place of the original job.
        """
        s_job = job if isinstance(job, SchedulerJobInfo) else SchedulerJobInfo(job_information=job)
        job_info = s_job.job_information
        if not cls.can_split(s_job):
            raise ValueError(
                f"Job {getattr(job_info, 'job_name', 'unknown')} cannot be split into shot shards."
            )

        shot_counts = cls.resolve_shares(job_info.shots, shares)

        shards: Dict[str, JobInfo] = {}
        for index, shots in enumerate(shot_counts):
            shard_name = f"{job_info.job_name}_shot{index}"
            shards[shard_name] = replace(
                job_info,
                job_name=shard_name,
                shots=shots,
                parent_job=None,  # Only the logical job takes part in cut reconstruction
                children_jobs=None,
                cutting_context=None,
                shot_parent=job_info,
                shot_shards=None,
            )
        job_info.shot_shards = shards

        return {
            name: SchedulerJobInfo(
                job_information=shard,
                assigned_machine=None,
                dispatch_order=None,
                depends_on=list(s_job.depends_on) if s_job.depends_on else None,
            )
            for name, shard in shards.items()
        }
