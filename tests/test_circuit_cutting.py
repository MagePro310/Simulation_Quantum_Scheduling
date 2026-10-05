import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark

from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.ibm_simulator.sim_machine5qubits import FakeBelemV2, FakeBogotaV2
from source.flow.schedule.circuit_cutter import GreedyCircuitCutter
from source.flow.schedule.pre_schedule import PreSchedulePhase


def test_greedy_partition_labels():
    cutter = GreedyCircuitCutter()
    # 7 qubits on 5-qubit machine -> 5 on A, 2 on B
    labels = cutter.get_greedy_partition_labels(7, 5)
    assert labels == ["A", "A", "A", "A", "A", "B", "B"]
    assert labels.count("A") == 5
    assert labels.count("B") == 2

    # 12 qubits on 5-qubit machine -> 5 on A, 5 on B, 2 on C
    labels_12 = cutter.get_greedy_partition_labels(12, 5)
    assert labels_12 == ["A"] * 5 + ["B"] * 5 + ["C"] * 2

    # Fits directly: 4 qubits on 5-qubit machine
    labels_4 = cutter.get_greedy_partition_labels(4, 5)
    assert labels_4 == ["A"] * 4


def test_half_partition_labels():
    cutter = GreedyCircuitCutter()
    # 7 qubits on 5-qubit machine -> split into halves: [4, 3] -> 4 on A, 3 on B
    labels = cutter.get_half_partition_labels(7, 5)
    assert labels == ["A", "A", "A", "A", "B", "B", "B"]
    assert labels.count("A") == 4
    assert labels.count("B") == 3

    # 12 qubits on 5-qubit machine -> split into halves: 12 -> 6, 6 -> 3, 3, 3, 3
    labels_12 = cutter.get_half_partition_labels(12, 5)
    assert labels_12 == ["A"] * 3 + ["B"] * 3 + ["C"] * 3 + ["D"] * 3

    # Fits directly: 4 qubits on 5-qubit machine
    labels_4 = cutter.get_half_partition_labels(4, 5)
    assert labels_4 == ["A"] * 4



def test_can_fit():
    cutter = GreedyCircuitCutter()
    assert not cutter.can_fit(7, 5)
    assert cutter.can_fit(5, 5)
    assert cutter.can_fit(3, 5)


def test_circuit_cutter_decomposition():
    cutter = GreedyCircuitCutter()
    qc = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    parent_job = JobInfo(job_name="job_test_7q", circuit=qc, num_qubits=7, shots=1024)

    children = cutter.cut_circuit(parent_job, max_capacity=5)

    assert len(children) == 2
    assert "job_test_7q_sub_A" in children
    assert "job_test_7q_sub_B" in children

    child_A = children["job_test_7q_sub_A"]
    child_B = children["job_test_7q_sub_B"]

    assert child_A.num_qubits == 5
    assert child_B.num_qubits == 2
    assert child_A.parentJob is parent_job
    assert child_B.parentJob is parent_job
    assert parent_job.childrenJobs == children
    assert parent_job.cutting_context is not None
    assert parent_job.cutting_overhead == 9.0
    assert child_A.cutting_overhead == 9.0
    assert child_B.cutting_overhead == 9.0


def test_circuit_cutter_half_decomposition():
    cutter = GreedyCircuitCutter()
    qc = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    parent_job = JobInfo(job_name="job_test_7q_half", circuit=qc, num_qubits=7, shots=1024)

    children = cutter.cut_circuit(parent_job, max_capacity=5, policy="half")

    assert len(children) == 2
    assert "job_test_7q_half_sub_A" in children
    assert "job_test_7q_half_sub_B" in children

    child_A = children["job_test_7q_half_sub_A"]
    child_B = children["job_test_7q_half_sub_B"]

    # Half cut splits 7 qubits into [4, 3]
    assert child_A.num_qubits == 4
    assert child_B.num_qubits == 3
    assert child_A.parentJob is parent_job
    assert child_B.parentJob is parent_job
    assert parent_job.childrenJobs == children
    assert parent_job.cutting_context is not None
    assert parent_job.cutting_context.policy == "half"
    assert parent_job.cutting_overhead == 9.0


def test_pre_schedule_phase_integration():
    pre_phase = PreSchedulePhase()
    qc_small = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)
    qc_large = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)

    origin_jobs = {
        "job_small": JobInfo(job_name="job_small", circuit=qc_small, num_qubits=3, shots=1024),
        "job_large": JobInfo(job_name="job_large", circuit=qc_large, num_qubits=7, shots=1024),
    }

    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    scheduled = pre_phase.execute(origin_jobs, machines)

    # job_small should remain intact
    assert "job_small" in scheduled
    assert scheduled["job_small"].job_information.num_qubits == 3

    # job_large should be replaced by subcircuits
    assert "job_large" not in scheduled
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled
    assert scheduled["job_large_sub_A"].job_information.num_qubits == 5
    assert scheduled["job_large_sub_B"].job_information.num_qubits == 2
    assert origin_jobs["job_large"].cutting_overhead == 9.0


def test_pre_schedule_phase_half_policy():
    pre_phase = PreSchedulePhase(cutting_policy="half")
    qc_large = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)

    origin_jobs = {
        "job_large": JobInfo(job_name="job_large", circuit=qc_large, num_qubits=7, shots=1024),
    }

    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    scheduled = pre_phase.execute(origin_jobs, machines)

    assert "job_large" not in scheduled
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled
    # Half cut policy yields 4 qubits and 3 qubits
    assert scheduled["job_large_sub_A"].job_information.num_qubits == 4
    assert scheduled["job_large_sub_B"].job_information.num_qubits == 3



def test_cutting_overhead_aggregation():
    from source.component.dataclass.result_schedule import ExecutionSummary
    from source.flow.execution.metrics_calculator import MetricsCalculator
    from source.component.dataclass.job_info import ExecutionResult

    summary = ExecutionSummary()
    # Simulate two cut jobs: one with overhead 81, another with overhead 30, and one uncut job (overhead 0)
    job1 = JobInfo(job_name="job1", cutting_overhead=81.0)
    job2 = JobInfo(job_name="job2", cutting_overhead=30.0)
    job3 = JobInfo(job_name="job3", cutting_overhead=0.0)

    results = {
        "job1": ExecutionResult(job_info=job1, status="SUCCEEDED", cutting_overhead=81.0, start_time=0.0, end_time=1.0),
        "job2": ExecutionResult(job_info=job2, status="SUCCEEDED", cutting_overhead=30.0, start_time=1.0, end_time=2.0),
        "job3": ExecutionResult(job_info=job3, status="SUCCEEDED", cutting_overhead=0.0, start_time=2.0, end_time=3.0),
    }

    MetricsCalculator.calculate_metrics(summary, results, machines={}, now=3.0)
    # Total cutting overhead must sum: 81 + 30 + 0 = 111
    assert summary.total_cutting_overhead == 111.0

