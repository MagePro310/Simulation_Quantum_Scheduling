from types import SimpleNamespace

from component.dataclass.job_info import ExecutionResult, JobInfo
from flow.execution.post_execution_analysis import PostExecution


def test_update_job_info_with_results_uses_machine_order_as_runtime_clock():
    scheduler_job_simulation = {
        "machine_a": [
            SimpleNamespace(
                job_info=[JobInfo(job_name="job1"), JobInfo(job_name="job2")],
                distribution_no_noise={"0": 5},
                distribution_with_noise={"0": 5},
                execution_time=5,
            ),
            SimpleNamespace(
                job_info=[JobInfo(job_name="job3")],
                distribution_no_noise={"1": 2},
                distribution_with_noise={"1": 2},
                execution_time=2,
            ),
        ],
        "machine_b": [
            SimpleNamespace(
                job_info=[JobInfo(job_name="job4")],
                distribution_no_noise={"0": 3},
                distribution_with_noise={"0": 3},
                execution_time=3,
            ),
        ],
    }

    results = PostExecution().update_job_info_with_results(scheduler_job_simulation)

    assert set(results) == {"job1", "job2", "job3", "job4"}

    assert results["job1"].assigned_machine == "machine_a"
    assert results["job1"].start_time == 0.0
    assert results["job1"].end_time == 5.0
    assert results["job1"].execution_time == 5.0
    assert results["job1"].distribution_no_noise == {"0": 5}
    assert results["job1"].distribution_with_noise == {"0": 5}

    assert results["job2"].assigned_machine == "machine_a"
    assert results["job2"].start_time == 0.0
    assert results["job2"].end_time == 5.0
    assert results["job2"].execution_time == 5.0

    assert results["job3"].assigned_machine == "machine_a"
    assert results["job3"].start_time == 5.0
    assert results["job3"].end_time == 7.0
    assert results["job3"].execution_time == 2.0

    assert results["job4"].assigned_machine == "machine_b"
    assert results["job4"].start_time == 0.0
    assert results["job4"].end_time == 3.0
    assert results["job4"].execution_time == 3.0

    assert results["job1"].fidelity is not None


def test_draw_gantt_chart_writes_png(tmp_path):
    output_path = tmp_path / "execution_gantt_chart.png"
    execution_results = {
        "job1": ExecutionResult(
            job_info=JobInfo(job_name="job1"),
            assigned_machine="machine_a",
            start_time=0.0,
            end_time=5.0,
            execution_time=5.0,
        ),
        "job2": ExecutionResult(
            job_info=JobInfo(job_name="job2"),
            assigned_machine="machine_a",
            start_time=5.0,
            end_time=7.0,
            execution_time=2.0,
        ),
        "job3": ExecutionResult(
            job_info=JobInfo(job_name="job3"),
            assigned_machine="machine_b",
            start_time=0.0,
            end_time=3.0,
            execution_time=3.0,
        ),
    }

    PostExecution().draw_gantt_chart(
        execution_results,
        output_path=str(output_path),
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
