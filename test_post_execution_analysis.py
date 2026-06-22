from types import SimpleNamespace

from component.dataclass.job_info import (
    ExecutionResult,
    JobInfo,
    MachineExecutionResult,
)
from flow.execution.post_execution_analysis import PostExecution
from qiskit import QuantumCircuit


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


def test_update_job_info_marginalizes_merged_distributions_per_job():
    job1 = JobInfo(job_name="job1", circuit=QuantumCircuit(3, 3))
    job2 = JobInfo(job_name="job2", circuit=QuantumCircuit(2, 2))
    scheduler_job_simulation = {
        "machine_a": [
            SimpleNamespace(
                job_info=[job1, job2],
                distribution_no_noise={
                    "00000": 10,
                    "01001": 20,
                    "10001": 30,
                    "11111": 40,
                },
                distribution_with_noise={
                    "00000": 5,
                    "01001": 25,
                    "10001": 35,
                    "11111": 35,
                },
                execution_time=5,
            ),
        ],
    }

    results = PostExecution().update_job_info_with_results(
        scheduler_job_simulation
    )

    # Qiskit renders the lowest classical-bit indices on the right. Job 1 was
    # composed first, so it owns those three rightmost bits.
    assert results["job1"].distribution_no_noise == {
        "000": 10,
        "001": 50,
        "111": 40,
    }
    assert results["job1"].distribution_with_noise == {
        "000": 5,
        "001": 60,
        "111": 35,
    }
    assert results["job2"].distribution_no_noise == {
        "00": 10,
        "01": 20,
        "10": 30,
        "11": 40,
    }
    assert results["job2"].distribution_with_noise == {
        "00": 5,
        "01": 25,
        "10": 35,
        "11": 35,
    }
    assert sum(results["job1"].distribution_no_noise.values()) == 100
    assert sum(results["job2"].distribution_no_noise.values()) == 100
    assert results["job1"].fidelity != results["job2"].fidelity


def test_update_machine_info_calculates_qubit_time_utilization():
    machines = {
        "machine_a": SimpleNamespace(num_qubits=10),
        "machine_idle": SimpleNamespace(num_qubits=5),
    }
    scheduler_job_simulation = {
        "machine_a": [
            SimpleNamespace(
                job_info=[
                    JobInfo(job_name="job1", circuit=QuantumCircuit(2)),
                    JobInfo(job_name="job2", circuit=QuantumCircuit(3)),
                ],
                execution_time=4,
            ),
            SimpleNamespace(
                job_info=[
                    JobInfo(job_name="job3", circuit=QuantumCircuit(4)),
                ],
                execution_time=6,
            ),
            SimpleNamespace(
                job_info=[
                    JobInfo(job_name="job4", circuit=QuantumCircuit(9)),
                ],
                execution_time=None,
            ),
        ],
    }

    results = PostExecution().update_machine_info_with_results(
        machines,
        scheduler_job_simulation,
    )

    assert set(results) == {"machine_a", "machine_idle"}
    assert isinstance(results["machine_a"], MachineExecutionResult)
    assert results["machine_a"].machine_name == "machine_a"
    assert results["machine_a"].utilization == 0.44
    assert isinstance(results["machine_idle"], MachineExecutionResult)
    assert results["machine_idle"].utilization == 0.0


def test_update_machine_info_rejects_invalid_machine_capacity():
    machines = {"machine_a": SimpleNamespace(num_qubits=0)}

    try:
        PostExecution().update_machine_info_with_results(machines, {})
    except ValueError as error:
        assert "positive num_qubits" in str(error)
    else:
        raise AssertionError("Expected invalid machine capacity to raise ValueError")


def test_update_machine_info_requires_job_qubit_information():
    machines = {"machine_a": SimpleNamespace(num_qubits=5)}
    scheduler_job_simulation = {
        "machine_a": [
            SimpleNamespace(
                job_info=[JobInfo(job_name="job1")],
                execution_time=2,
            ),
        ],
    }

    try:
        PostExecution().update_machine_info_with_results(
            machines,
            scheduler_job_simulation,
        )
    except ValueError as error:
        assert "circuit.num_qubits" in str(error)
    else:
        raise AssertionError("Expected missing job qubits to raise ValueError")
