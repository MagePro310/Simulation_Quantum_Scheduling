"""Characterization tests for flow/schedule/post_schedule.py::PostSchedulePhase.

These document the module's real, current behavior (verified by running the
implementation) rather than proposing fixes. In particular: an earlier code
reading suspected that jobs which only *partially* overlap a sub-interval
would be silently excluded from it. That does NOT actually happen: interval
breakpoints are always the union of every job's own start/end time on that
machine, so any job whose window genuinely overlaps a sub-interval is
mathematically guaranteed to fully contain it (its own start/end can never
fall strictly inside a gap between two consecutive breakpoints). The
`test_execute_includes_every_job_that_overlaps_a_subinterval` test below
verifies this directly with a staggered 3-job overlap chain.
"""
from component.dataclass.job_info import JobInfo, SchedulerJobInfo
from flow.schedule.post_schedule import PostSchedulePhase


def make_job(name, machine, start, end):
    return SchedulerJobInfo(
        job_information=JobInfo(job_name=name),
        scheduled_start_time=start,
        scheduled_end_time=end,
        assigned_machine=machine,
    )


def names(groups):
    return [[job.job_name for job in group] for group in groups]


def test_execute_returns_empty_dict_for_empty_scheduler_job():
    assert PostSchedulePhase().execute({}, {}) == {}


def test_execute_groups_sequential_jobs_by_assigned_machine():
    j1 = make_job("j1", "m1", 0, 2)
    j2 = make_job("j2", "m1", 2, 4)
    j3 = make_job("j3", "m2", 0, 3)

    result = PostSchedulePhase().execute({"j1": j1, "j2": j2, "j3": j3}, {})

    assert set(result.keys()) == {"m1", "m2"}
    assert names(result["m1"]) == [["j1"], ["j2"]]
    assert names(result["m2"]) == [["j3"]]


def test_execute_groups_jobs_with_none_assigned_machine_under_none_key():
    j4 = make_job("j4", None, 0, 1)

    result = PostSchedulePhase().execute({"j4": j4}, {})

    assert list(result.keys()) == [None]
    assert names(result[None]) == [["j4"]]


def test_execute_includes_every_job_that_overlaps_a_subinterval():
    # A staggered overlap chain: P and R never directly overlap, but each
    # overlaps Q. Every sub-interval's active-job list correctly includes
    # exactly the jobs genuinely running during it - no spurious exclusions.
    p = make_job("P", "m1", 0, 6)
    q = make_job("Q", "m1", 2, 8)
    r = make_job("R", "m1", 4, 10)

    result = PostSchedulePhase().execute({"P": p, "Q": q, "R": r}, {})

    assert names(result["m1"]) == [
        ["P"],
        ["P", "Q"],
        ["P", "Q", "R"],
        ["Q", "R"],
        ["R"],
    ]


def test_execute_silently_drops_a_standalone_zero_duration_job():
    # A job with scheduled_start_time == scheduled_end_time produces no
    # [t_start, t_end) slice at all, so it never appears in the result.
    zero_job = make_job("Z", "m1", 5, 5)

    result = PostSchedulePhase().execute({"Z": zero_job}, {})

    assert result["m1"] == []


def test_execute_deduplicates_adjacent_slices_split_by_a_zero_duration_job():
    # Zmid's zero-duration window injects an extra breakpoint (t=5) that
    # splits Y's continuous [0, 10) span into two adjacent sub-intervals
    # with an identical active-job list ([Y]); these collapse into one
    # entry instead of appearing twice.
    y = make_job("Y", "m1", 0, 10)
    z_mid = make_job("Zmid", "m1", 5, 5)

    result = PostSchedulePhase().execute({"Y": y, "Zmid": z_mid}, {})

    assert names(result["m1"]) == [["Y"]]
