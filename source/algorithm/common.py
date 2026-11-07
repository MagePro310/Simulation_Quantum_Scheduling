"""Common helper functions for quantum scheduling algorithms."""

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.help_function.estimated_time import EstimatedTime


def estimate_job_duration(job: SchedulerJobInfo) -> float:
    """Estimate duration using default shots and a minimum depth of one."""
    if job.job_information is None:
        return 0.0
    return EstimatedTime().estimate_execution_time_without_machine(job.job_information)


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
