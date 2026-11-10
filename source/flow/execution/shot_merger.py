"""Merge results of jobs whose shots ran in several pieces.

Used both when one job runs over several batches and when a job's shots were split
into shards on different machines (see ShotDistributionHelper).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from qiskit.primitives.containers import BitArray, DataBin, PrimitiveResult, PubResult

from source.models.job import ExecutionResult, JobInfo
from source.utils.fidelity import (
    compute_hellinger_fidelity,
    compute_total_variation_distance,
)

SHOT_MERGE_MACHINE = "shot_merge"
_QPD_FIELDS = ("observable_measurements", "qpd_measurements")


def merge_counts(*distributions: dict[str, int] | None) -> dict[str, int]:
    """Add measurement count dictionaries."""
    total: Counter = Counter()
    for distribution in distributions:
        if distribution:
            total.update(distribution)
    return dict(total)


def merge_primitive_results(results: Iterable[Any | None]) -> Any | None:
    """Concatenate the shots of QPD subexperiment results pub by pub.

    Every input must come from the same subexperiments, so they have the same number
    of pubs and the same data fields. None entries are ignored; a single result is
    returned unchanged.
    """
    present = [r for r in results if r is not None]
    if not present:
        return None
    if len(present) == 1:
        return present[0]

    num_pubs = len(present[0])
    if any(len(r) != num_pubs for r in present):
        raise ValueError("Cannot merge subexperiment results with different numbers of pubs.")

    pubs = []
    for index in range(num_pubs):
        fields = {}
        for name in _QPD_FIELDS:
            arrays = [getattr(r[index].data, name, None) for r in present]
            if all(isinstance(a, BitArray) for a in arrays):
                fields[name] = BitArray.concatenate_shots(arrays)
            elif any(a is not None for a in arrays):
                raise ValueError(f"Subexperiment results disagree on field '{name}'.")
        pubs.append(PubResult(DataBin(**fields)))
    return PrimitiveResult(pubs)


def merged_busy_time(results: Iterable[ExecutionResult]) -> float:
    """Return the time at least one of the results was running, counting overlaps once."""
    intervals = sorted(
        (r.start_time, r.end_time)
        for r in results
        if r.start_time is not None and r.end_time is not None
    )
    busy = 0.0
    merged_end = None
    for start, end in intervals:
        if merged_end is None or start > merged_end:
            busy += end - start
            merged_end = end
        elif end > merged_end:
            busy += end - merged_end
            merged_end = end
    return busy


def shard_results_of(logical_job: JobInfo, results: dict[str, ExecutionResult]) -> list[ExecutionResult]:
    """Return the execution results of a logical job's shards, in shard order."""
    return [results[name] for name in (logical_job.shot_shards or {}) if name in results]


def build_logical_result(
    logical_job: JobInfo,
    shard_results: list[ExecutionResult],
) -> ExecutionResult:
    """Merge succeeded shards into one result under the logical job."""
    no_noise = merge_counts(*(r.distribution_no_noise for r in shard_results))
    with_noise = merge_counts(*(r.distribution_with_noise for r in shard_results))
    starts = [r.start_time for r in shard_results if r.start_time is not None]
    ends = [r.end_time for r in shard_results if r.end_time is not None]

    return ExecutionResult(
        job_info=logical_job,
        assigned_machine=SHOT_MERGE_MACHINE,
        distribution_no_noise=no_noise,
        distribution_with_noise=with_noise,
        fidelity=compute_hellinger_fidelity(no_noise, with_noise),
        tvd=compute_total_variation_distance(no_noise, with_noise),
        cutting_overhead=logical_job.cutting_overhead,
        start_time=min(starts, default=None),
        end_time=max(ends, default=None),
        execution_time=merged_busy_time(shard_results),
        status="SUCCEEDED",
        requested_shots=logical_job.shots or sum(r.requested_shots for r in shard_results),
        completed_shots=sum(r.completed_shots for r in shard_results),
        sub_result=merge_primitive_results(r.sub_result for r in shard_results),
    )
