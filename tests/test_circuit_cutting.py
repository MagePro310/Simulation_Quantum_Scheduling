import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.component.ibm_simulator.sim_machine5qubits import FakeBelemV2, FakeBogotaV2
from source.flow.schedule.circuit_cutter import GreedyCircuitCutter, CircuitCutter, SchedulingCutterHelper
from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase
from source.algorithm.heuristic.FFD import FFD
from source.algorithm.heuristic.FFD_v2 import FFD_v2


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


def test_pre_schedule_phase_integration():
    """Test PreSchedulePhase with default greedy policy on oversized circuits."""
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

    # job_small fits within 5 qubits and must remain uncut in PreSchedulePhase
    assert "job_small" in scheduled
    assert scheduled["job_small"].job_information.num_qubits == 3

    # job_large exceeds 5 qubits and must be cut with greedy policy -> [5, 2]
    assert "job_large" not in scheduled
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled
    assert scheduled["job_large_sub_A"].job_information.num_qubits == 5
    assert scheduled["job_large_sub_B"].job_information.num_qubits == 2
    assert origin_jobs["job_large"].cutting_overhead == 9.0


def test_pre_schedule_phase_half_policy():
    """Test PreSchedulePhase with half cutting policy on oversized circuits."""
    pre_phase = PreSchedulePhase(exceed_cutting_policy="half")
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


def test_half_partition_labels_force_cut():
    cutter = GreedyCircuitCutter()
    # Without force_cut, circuits <= 5 remain uncut
    assert cutter.get_half_partition_labels(2, 5, force_cut=False) == ["A", "A"]
    assert cutter.get_half_partition_labels(3, 5, force_cut=False) == ["A", "A", "A"]

    # With force_cut=True, all circuits >= 2 are split in half
    assert cutter.get_half_partition_labels(2, 5, force_cut=True) == ["A", "B"]
    assert cutter.get_half_partition_labels(3, 5, force_cut=True) == ["A", "A", "B"]
    assert cutter.get_half_partition_labels(4, 5, force_cut=True) == ["A", "A", "B", "B"]


def test_pre_schedule_phase_set_policy_and_invariant():
    """Test policy setter and capacity invariant check in PreSchedulePhase."""
    pre_phase = PreSchedulePhase(exceed_cutting_policy="greedy")
    assert pre_phase.exceed_cutting_policy == "greedy"
    pre_phase.set_exceed_cutting_policy("half")
    assert pre_phase.exceed_cutting_policy == "half"

    # Test invariant validation raises ValueError when a job exceeds max_capacity
    violating_job = JobInfo(job_name="huge_job", num_qubits=10)
    scheduler_jobs = {
        "huge_job": SchedulerJobInfo(job_information=violating_job)
    }
    with pytest.raises(ValueError, match="Invariant violated"):
        PreSchedulePhase._verify_capacity_invariant(scheduler_jobs, max_capacity=5)


def test_scheduling_cutter_helper():
    """Test SchedulingCutterHelper chops eligible uncut circuits into smaller halves."""
    qc2 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=2)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    jobs = {
        "j2": SchedulerJobInfo(job_information=JobInfo(job_name="j2", circuit=qc2, num_qubits=2, shots=1024)),
        "j3": SchedulerJobInfo(job_information=JobInfo(job_name="j3", circuit=qc3, num_qubits=3, shots=1024)),
    }

    chopped = SchedulingCutterHelper.apply_half_cut_to_jobs(jobs, max_capacity=5)

    # j2 (2 qubits) chopped into 2 subcircuits of 1 qubit
    assert "j2" not in chopped
    assert "j2_sub_A" in chopped
    assert "j2_sub_B" in chopped
    assert chopped["j2_sub_A"].job_information.num_qubits == 1
    assert chopped["j2_sub_B"].job_information.num_qubits == 1

    # j3 (3 qubits) chopped into [2, 1] qubits
    assert "j3" not in chopped
    assert "j3_sub_A" in chopped
    assert "j3_sub_B" in chopped
    assert chopped["j3_sub_A"].job_information.num_qubits == 2
    assert chopped["j3_sub_B"].job_information.num_qubits == 1


def test_ffd_v2_cutting_and_reordering():
    """Test FFD_v2 autonomously chops incoming circuits and re-orders largest-first."""
    qc2 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=2)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    scheduler_job = {
        "j2": SchedulerJobInfo(job_information=JobInfo(job_name="j2", circuit=qc2, num_qubits=2, shots=1024)),
        "j3": SchedulerJobInfo(job_information=JobInfo(job_name="j3", circuit=qc3, num_qubits=3, shots=1024)),
    }

    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    ffd_v2 = FFD_v2()
    result = ffd_v2.execute(scheduler_job, machines)

    # All jobs were chopped: j3 -> [2, 1], j2 -> [1, 1]
    assert len(result) == 4
    assert "j3_sub_A" in result  # 2 qubits
    assert "j3_sub_B" in result  # 1 qubit
    assert "j2_sub_A" in result  # 1 qubit
    assert "j2_sub_B" in result  # 1 qubit

    # All subjobs must have an assigned machine and dispatch order
    for s_job in result.values():
        assert s_job.assigned_machine in machines
        assert s_job.dispatch_order is not None


def test_ffd_v2_end_to_end_flow():
    """Test full pipeline with PreSchedule, FFD_v2, and ConcreteExecutionPhase."""
    from source.flow.execution.orchestrator import ConcreteExecutionPhase

    qc2 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=2)
    qc7 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)

    origin_jobs = {
        "j2": JobInfo(job_name="j2", circuit=qc2, num_qubits=2, shots=1024),
        "j7": JobInfo(job_name="j7", circuit=qc7, num_qubits=7, shots=1024),
    }

    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    capture_res = ResultOfSchedule()
    phase = ConcreteSchedulePhase(algorithm=FFD_v2(), exceed_cutting_policy="greedy")
    scheduled = phase.execute(origin_jobs, machines, capture_res)

    # PreSchedule cuts j7 into [5, 2]
    # FFD_v2 cuts j2 into [1, 1] (j7's subcircuits are already cut, so they are not nested)
    assert "j7_sub_A" in scheduled
    assert "j7_sub_B" in scheduled
    assert "j2_sub_A" in scheduled
    assert "j2_sub_B" in scheduled

    # Run execution phase to ensure reconstruction succeeds
    exec_phase = ConcreteExecutionPhase()
    results = exec_phase.execute(machines, scheduled, capture_result_schedule=capture_res)

    # Both parent jobs must have reconstructed results
    assert "j7" in results
    assert "j2" in results
    assert results["j7"].status == "SUCCEEDED"
    assert results["j2"].status == "SUCCEEDED"
    assert results["j7"].reconstructed_distribution is not None
    assert results["j2"].reconstructed_distribution is not None


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


def test_modular_half_policy_helpers():
    from source.flow.schedule.cutting.half_policy import HalfCuttingPolicy

    policy = HalfCuttingPolicy()
    assert policy.name == "half"

    # Helper: _split_qubits_in_half
    assert policy._split_qubits_in_half(7) == (4, 3)
    assert policy._split_qubits_in_half(2) == (1, 1)
    assert policy._split_qubits_in_half(3) == (2, 1)

    # Helper: calculate_subcircuit_sizes
    assert policy.calculate_subcircuit_sizes(7, 5) == [4, 3]
    assert policy.calculate_subcircuit_sizes(12, 5) == [3, 3, 3, 3]
    assert policy.calculate_subcircuit_sizes(3, 5, force_cut=False) == [3]
    assert policy.calculate_subcircuit_sizes(3, 5, force_cut=True) == [2, 1]

    # Helper: convert_sizes_to_labels
    assert policy.convert_sizes_to_labels([4, 3]) == ["A", "A", "A", "A", "B", "B", "B"]
    assert policy.convert_sizes_to_labels([1, 1]) == ["A", "B"]


def test_modular_greedy_policy_helpers():
    from source.flow.schedule.cutting.greedy_policy import GreedyCuttingPolicy

    policy = GreedyCuttingPolicy()
    assert policy.name == "greedy"

    # Helper: calculate_greedy_sizes
    assert policy.calculate_greedy_sizes(7, 5) == [5, 2]
    assert policy.calculate_greedy_sizes(12, 5) == [5, 5, 2]
    assert policy.calculate_greedy_sizes(4, 5) == [4]

    # get_partition_labels
    assert policy.get_partition_labels(7, 5) == ["A"] * 5 + ["B"] * 2


def test_cutter_pipeline_helpers():
    from qiskit import QuantumCircuit
    from source.flow.schedule.cutting.cutter_pipeline import CircuitCutter, get_cutting_policy
    from source.flow.schedule.cutting.greedy_policy import GreedyCuttingPolicy
    from source.flow.schedule.cutting.half_policy import HalfCuttingPolicy

    cutter = CircuitCutter()

    # _resolve_policy & get_cutting_policy
    assert isinstance(cutter._resolve_policy("greedy"), GreedyCuttingPolicy)
    assert isinstance(cutter._resolve_policy("half"), HalfCuttingPolicy)
    assert isinstance(cutter._resolve_policy(GreedyCuttingPolicy()), GreedyCuttingPolicy)
    assert isinstance(get_cutting_policy("greedy"), GreedyCuttingPolicy)
    assert isinstance(get_cutting_policy("half"), HalfCuttingPolicy)

    # _prepare_clean_circuit
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    assert qc.num_clbits == 2
    clean = cutter._prepare_clean_circuit(qc)
    assert clean.num_clbits == 0
    assert clean.num_qubits == 2

    # _build_computational_observables
    pauli_list, z_strings = cutter._build_computational_observables(2)
    assert len(z_strings) == 4
    assert set(z_strings) == {"II", "IZ", "ZI", "ZZ"}
    assert len(pauli_list) == 4


def test_pre_schedule_phase_decomposed_helpers():
    from source.component.dataclass.job_info import JobInfo
    from source.component.dataclass.machine_characteristic import MachineCharacteristic
    from source.component.ibm_simulator.sim_machine5qubits import FakeBelemV2

    machines = {"belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5)}
    assert PreSchedulePhase._get_max_capacity(machines) == 5
    assert PreSchedulePhase._get_max_capacity({}) is None

    pre_phase = PreSchedulePhase(exceed_cutting_policy="half")
    job_7q = JobInfo(job_name="j7", num_qubits=7)
    job_3q = JobInfo(job_name="j3", num_qubits=3)

    # _is_oversized:
    assert pre_phase._is_oversized(job_7q, 5) is True
    assert pre_phase._is_oversized(job_3q, 5) is False

    # _wrap_uncut_job
    wrapped = pre_phase._wrap_uncut_job(job_3q)
    assert wrapped.job_information is job_3q
    assert wrapped.assigned_machine is None


def test_mandatory_cut_greedy_with_optional_cut_half():
    """Verify primary user scenario: Mandatory exceed with greedy, optional cut with half."""
    qc7 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    origin_jobs = {
        "job_large": JobInfo(job_name="job_large", circuit=qc7, num_qubits=7, shots=1024),
        "job_small": JobInfo(job_name="job_small", circuit=qc3, num_qubits=3, shots=1024),
    }
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    # Configure: exceed with greedy, optional with half enabled
    pre_phase = PreSchedulePhase(
        exceed_cutting_policy="greedy",
        enable_optional_cutting=True,
        optional_cutting_policy="half",
    )
    scheduled = pre_phase.execute(origin_jobs, machines)

    # 1. job_large (7q > 5q) was cut in Stage 1 using greedy into [5, 2]
    assert "job_large" not in scheduled
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled
    assert scheduled["job_large_sub_A"].job_information.num_qubits == 5
    assert scheduled["job_large_sub_B"].job_information.num_qubits == 2

    # 2. job_small (3q <= 5q) was cut in Stage 2 using half into [2, 1]
    assert "job_small" not in scheduled
    assert "job_small_sub_A" in scheduled
    assert "job_small_sub_B" in scheduled
    assert scheduled["job_small_sub_A"].job_information.num_qubits == 2
    assert scheduled["job_small_sub_B"].job_information.num_qubits == 1

    # 3. Subcircuits from job_large were NOT cut again in Stage 2 (1-level hierarchy preserved)
    assert "job_large_sub_A_sub_A" not in scheduled
    assert "job_large_sub_B_sub_A" not in scheduled


def test_mandatory_cut_half_with_optional_cut_half():
    """Verify both stages using half cutting."""
    qc7 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    origin_jobs = {
        "job_large": JobInfo(job_name="job_large", circuit=qc7, num_qubits=7, shots=1024),
        "job_small": JobInfo(job_name="job_small", circuit=qc3, num_qubits=3, shots=1024),
    }
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
    }

    pre_phase = PreSchedulePhase(
        exceed_cutting_policy="half",
        enable_optional_cutting=True,
        optional_cutting_policy="half",
    )
    scheduled = pre_phase.execute(origin_jobs, machines)

    # job_large (7q) cut with half into [4, 3]
    assert scheduled["job_large_sub_A"].job_information.num_qubits == 4
    assert scheduled["job_large_sub_B"].job_information.num_qubits == 3

    # job_small (3q) cut with half into [2, 1]
    assert scheduled["job_small_sub_A"].job_information.num_qubits == 2
    assert scheduled["job_small_sub_B"].job_information.num_qubits == 1


def test_mandatory_cut_exceed_only_preserves_smaller_circuits():
    """Verify that when optional cutting is disabled, smaller circuits remain uncut."""
    qc7 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    origin_jobs = {
        "job_large": JobInfo(job_name="job_large", circuit=qc7, num_qubits=7, shots=1024),
        "job_small": JobInfo(job_name="job_small", circuit=qc3, num_qubits=3, shots=1024),
    }
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
    }

    pre_phase = PreSchedulePhase(
        exceed_cutting_policy="greedy",
        enable_optional_cutting=False,
    )
    scheduled = pre_phase.execute(origin_jobs, machines)

    # job_large (7q > 5q) MUST be cut
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled

    # job_small (3q <= 5q) must remain UNCUT
    assert "job_small" in scheduled
    assert scheduled["job_small"].job_information.num_qubits == 3


def test_scheduling_cutter_helper_supports_custom_policy():
    """Verify SchedulingCutterHelper.apply_cutting_to_jobs accepts dynamic policy."""
    qc4 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=4)
    jobs = {
        "j4": SchedulerJobInfo(job_information=JobInfo(job_name="j4", circuit=qc4, num_qubits=4, shots=1024)),
    }

    # Apply half cut via general apply_cutting_to_jobs method
    chopped = SchedulingCutterHelper.apply_cutting_to_jobs(jobs, max_capacity=5, policy="half")
    assert "j4" not in chopped
    assert "j4_sub_A" in chopped
    assert "j4_sub_B" in chopped
    assert chopped["j4_sub_A"].job_information.num_qubits == 2
    assert chopped["j4_sub_B"].job_information.num_qubits == 2


def test_concrete_schedule_phase_captures_both_stages():
    """Verify ConcreteSchedulePhase captures exceed and optional cutting metadata."""
    capture_res = ResultOfSchedule()
    phase = ConcreteSchedulePhase(
        algorithm=FFD(),
        exceed_cutting_policy="greedy",
        enable_optional_cutting=True,
        optional_cutting_policy="half",
    )

    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)
    origin_jobs = {"j3": JobInfo(job_name="j3", circuit=qc3, num_qubits=3, shots=1024)}
    machines = {"belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5)}

    phase.execute(origin_jobs, machines, capture_res)

    assert capture_res.exceed_cutting_policy == "greedy"
    assert capture_res.optional_cutting is True
    assert capture_res.optional_cutting_policy == "half"
    assert capture_res.ScheduleLatency > 0.0

    from source.component.help_function.result_serialization import serialize_result
    serialized = serialize_result(capture_res)
    assert serialized["ScheduleLatency"] == capture_res.ScheduleLatency
    assert serialized["schedule_latency"] == capture_res.ScheduleLatency


def test_end_to_end_ffd_with_optional_cutting():
    """Full end-to-end integration test: Input -> PreSchedule -> FFD -> Execution -> Reconstruct."""
    from source.flow.execution.orchestrator import ConcreteExecutionPhase

    qc7 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=7)
    qc3 = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=3)

    origin_jobs = {
        "job_large": JobInfo(job_name="job_large", circuit=qc7, num_qubits=7, shots=1024),
        "job_small": JobInfo(job_name="job_small", circuit=qc3, num_qubits=3, shots=1024),
    }
    machines = {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    capture_res = ResultOfSchedule()
    phase = ConcreteSchedulePhase(
        algorithm=FFD(),
        exceed_cutting_policy="greedy",
        enable_optional_cutting=True,
        optional_cutting_policy="half",
    )
    scheduled = phase.execute(origin_jobs, machines, capture_res)

    # 4 subcircuits generated:
    # job_large -> job_large_sub_A (5q), job_large_sub_B (2q)
    # job_small -> job_small_sub_A (2q), job_small_sub_B (1q)
    assert len(scheduled) == 4
    assert "job_large_sub_A" in scheduled
    assert "job_large_sub_B" in scheduled
    assert "job_small_sub_A" in scheduled
    assert "job_small_sub_B" in scheduled

    # Execute simulation and reconstruction
    exec_phase = ConcreteExecutionPhase()
    results = exec_phase.execute(machines, scheduled, capture_result_schedule=capture_res)

    # Both parent circuits must succeed and have reconstructed distributions
    assert results["job_large"].status == "SUCCEEDED"
    assert results["job_small"].status == "SUCCEEDED"
    assert results["job_large"].reconstructed_distribution is not None
    assert results["job_small"].reconstructed_distribution is not None

