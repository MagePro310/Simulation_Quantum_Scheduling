"""Common helper functions for quantum scheduling algorithms."""

from __future__ import annotations

from source.models.job import JobInfo, SchedulerJobInfo
from source.utils.timing import estimate_job_duration


def merge_dependencies(
    existing_dependencies: list[JobInfo | None],
    new_dependencies: list[JobInfo],
) -> list[JobInfo | None]:
    """Keep dependency order and deduplicate by object identity."""
    dependencies: list[JobInfo | None] = []
    seen_ids: set[int] = set()
    for dependency in existing_dependencies + new_dependencies:
        dependency_id = id(dependency)
        if dependency_id not in seen_ids:
            dependencies.append(dependency)
            seen_ids.add(dependency_id)
    return dependencies


__all__ = ["estimate_job_duration", "merge_dependencies"]
