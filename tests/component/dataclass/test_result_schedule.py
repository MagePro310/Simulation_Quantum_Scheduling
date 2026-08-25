"""Unit tests for ResultOfSchedule.calculate_metrics (component/dataclass/result_schedule.py)."""
from component.dataclass.job_info import JobInfo, SchedulerJobInfo
from component.dataclass.result_schedule import ResultOfSchedule


def make_job(name, arrival, start, end):
    return SchedulerJobInfo(
        job_information=JobInfo(job_name=name, arrival_time=arrival),
        scheduled_start_time=start,
        scheduled_end_time=end,
    )


def test_calculate_metrics_with_no_jobs_leaves_defaults_untouched():
    result = ResultOfSchedule()
    result.calculate_metrics({})

    assert result.makespan == 0.0
    assert result.totalTurnaroundTime == 0.0
    assert result.jobCompletionRate == 0.0


def test_calculate_metrics_computes_makespan_as_max_scheduled_end_time():
    jobs = {
        "j1": make_job("j1", arrival=0.0, start=0.0, end=5.0),
        "j2": make_job("j2", arrival=1.0, start=2.0, end=6.0),
        "j3": make_job("j3", arrival=0.0, start=5.0, end=10.0),
    }
    result = ResultOfSchedule()
    result.calculate_metrics(jobs)

    assert result.makespan == 10.0


def test_calculate_metrics_computes_totals_and_averages_for_turnaround_waiting_response():
    jobs = {
        "j1": make_job("j1", arrival=0.0, start=0.0, end=5.0),
        "j2": make_job("j2", arrival=1.0, start=2.0, end=6.0),
        "j3": make_job("j3", arrival=0.0, start=5.0, end=10.0),
    }
    result = ResultOfSchedule()
    result.calculate_metrics(jobs)

    # turnaround = end - arrival: (5-0) + (6-1) + (10-0) = 5 + 5 + 10 = 20
    assert result.totalTurnaroundTime == 20.0
    assert result.averageTurnaroundTime == 20.0 / 3

    # waiting = start - arrival: (0-0) + (2-1) + (5-0) = 0 + 1 + 5 = 6
    assert result.totalWaitingTime == 6.0
    assert result.averageWaitingTime == 2.0

    # response time uses the same formula as waiting time in this implementation
    assert result.totalResponseTime == 6.0
    assert result.averageResponseTime == 2.0


def test_calculate_metrics_defaults_missing_arrival_time_to_zero():
    jobs = {"j1": make_job("j1", arrival=None, start=1.0, end=3.0)}
    result = ResultOfSchedule()
    result.calculate_metrics(jobs)

    assert result.totalTurnaroundTime == 3.0  # 3 - 0
    assert result.totalWaitingTime == 1.0  # 1 - 0


def test_calculate_metrics_computes_job_completion_rate_as_jobs_over_makespan():
    jobs = {
        "j1": make_job("j1", arrival=0.0, start=0.0, end=5.0),
        "j2": make_job("j2", arrival=1.0, start=2.0, end=6.0),
        "j3": make_job("j3", arrival=0.0, start=5.0, end=10.0),
    }
    result = ResultOfSchedule()
    result.calculate_metrics(jobs)

    assert result.jobCompletionRate == 3 / 10.0


def test_calculate_metrics_all_zero_end_time_yields_zero_completion_rate_without_crashing():
    # Degenerate case: every job has scheduled_end_time == 0.0, so makespan
    # stays 0.0. jobCompletionRate is guarded to 0.0 instead of raising
    # ZeroDivisionError (num_jobs / makespan).
    jobs = {
        "j1": make_job("j1", arrival=0.0, start=0.0, end=0.0),
        "j2": make_job("j2", arrival=0.0, start=0.0, end=0.0),
    }
    result = ResultOfSchedule()
    result.calculate_metrics(jobs)

    assert result.makespan == 0.0
    assert result.jobCompletionRate == 0.0
