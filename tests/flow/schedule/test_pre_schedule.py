"""Unit tests for flow/schedule/pre_schedule.py::PreSchedulePhase."""
import pytest
from qiskit import QuantumCircuit

from component.dataclass.job_info import JobInfo, SchedulerJobInfo
from flow.schedule.pre_schedule import PreSchedulePhase


def circuit_with_gate(num_qubits: int, gate: str = "h") -> QuantumCircuit:
    """A QuantumCircuit with an instruction.

    NOTE: qiskit's QuantumCircuit.__bool__ reflects instruction count, not
    qubit count - an empty QuantumCircuit(n) is falsy. Since production code
    does `if info.job_information.circuit`, a truly empty circuit would be
    silently treated as "no circuit". Tests use circuits with at least one
    gate to exercise the intended "circuit present" path.
    """
    qc = QuantumCircuit(num_qubits)
    getattr(qc, gate)(0)
    return qc


def make_job(name, num_qubits, start, end, gate="h"):
    circuit = circuit_with_gate(num_qubits, gate)
    return SchedulerJobInfo(
        job_information=JobInfo(job_name=name, circuit=circuit),
        scheduled_start_time=start,
        scheduled_end_time=end,
    )


# ---------------------------------------------------------------------------
# get_circuit_for_compose
# ---------------------------------------------------------------------------


def test_get_circuit_for_compose_returns_empty_list_for_empty_dict():
    assert PreSchedulePhase.get_circuit_for_compose({}) == []


def test_get_circuit_for_compose_skips_jobs_with_no_job_information():
    job = SchedulerJobInfo(job_information=None, scheduled_start_time=0, scheduled_end_time=1)
    assert PreSchedulePhase.get_circuit_for_compose({"a": job}) == []


def test_get_circuit_for_compose_skips_jobs_with_no_circuit():
    job = SchedulerJobInfo(
        job_information=JobInfo(job_name="h", circuit=None),
        scheduled_start_time=0,
        scheduled_end_time=1,
    )
    assert PreSchedulePhase.get_circuit_for_compose({"h": job}) == []


def test_get_circuit_for_compose_returns_single_circuit_for_one_job():
    job = make_job("j1", num_qubits=2, start=0, end=5)
    result = PreSchedulePhase.get_circuit_for_compose({"j1": job})

    assert len(result) == 1
    assert result[0] is job.job_information.circuit


def test_get_circuit_for_compose_keeps_non_overlapping_jobs_as_separate_entries():
    job_a = make_job("A", num_qubits=1, start=0, end=2)
    job_b = make_job("B", num_qubits=1, start=2, end=4)  # touches, does not overlap

    result = PreSchedulePhase.get_circuit_for_compose({"A": job_a, "B": job_b})

    assert len(result) == 2
    assert result[0] is job_a.job_information.circuit
    assert result[1] is job_b.job_information.circuit


def test_get_circuit_for_compose_composes_overlapping_jobs_into_one_tensor_product():
    job_c = make_job("C", num_qubits=2, start=0, end=5)
    job_d = make_job("D", num_qubits=3, start=2, end=6)  # overlaps C

    result = PreSchedulePhase.get_circuit_for_compose({"C": job_c, "D": job_d})

    assert len(result) == 1
    assert result[0].num_qubits == 5


def test_get_circuit_for_compose_groups_three_jobs_by_overlap_correctly():
    job_e = make_job("E", num_qubits=1, start=0, end=3)
    job_f = make_job("F", num_qubits=1, start=2, end=5)  # overlaps E
    job_g = make_job("G", num_qubits=1, start=6, end=8)  # separate window

    result = PreSchedulePhase.get_circuit_for_compose({"E": job_e, "F": job_f, "G": job_g})

    assert len(result) == 2
    assert result[0].num_qubits == 2  # E + F composed
    assert result[1] is job_g.job_information.circuit


# ---------------------------------------------------------------------------
# compose_multiple_circuits
# ---------------------------------------------------------------------------


def test_compose_multiple_circuits_raises_value_error_for_fewer_than_two_circuits():
    with pytest.raises(ValueError, match="At least 2 circuits"):
        PreSchedulePhase.compose_multiple_circuits(circuit_with_gate(1))


def test_compose_multiple_circuits_combined_qubit_count_equals_sum_of_inputs():
    combined = PreSchedulePhase.compose_multiple_circuits(
        circuit_with_gate(2), circuit_with_gate(3)
    )
    assert combined.num_qubits == 5


def test_compose_multiple_circuits_preserves_argument_order_in_qubit_index_order():
    qc_x = QuantumCircuit(1, name="x")
    qc_x.x(0)
    qc_y = QuantumCircuit(1, name="y")
    qc_y.y(0)
    qc_z = QuantumCircuit(1, name="z")
    qc_z.z(0)

    combined = PreSchedulePhase.compose_multiple_circuits(qc_x, qc_y, qc_z)

    assert combined.num_qubits == 3
    gate_by_qubit = {
        combined.find_bit(instr.qubits[0]).index: instr.operation.name
        for instr in combined.data
    }
    assert gate_by_qubit == {0: "x", 1: "y", 2: "z"}


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


def test_execute_produces_a_scheduler_job_info_per_input_job_name():
    origin = {
        "j1": JobInfo(job_name="j1", circuit=circuit_with_gate(1), arrival_time=0.0),
        "j2": JobInfo(job_name="j2", circuit=circuit_with_gate(2), arrival_time=0.0),
    }
    result = PreSchedulePhase().execute(origin)

    assert set(result.keys()) == {"j1", "j2"}
    assert all(isinstance(v, SchedulerJobInfo) for v in result.values())


def test_execute_deep_copies_job_information_so_original_dict_is_unaffected():
    origin = {"j1": JobInfo(job_name="j1", circuit=circuit_with_gate(1), arrival_time=0.0)}
    result = PreSchedulePhase().execute(origin)

    assert result["j1"].job_information is not origin["j1"]
    result["j1"].job_information.job_name = "MUTATED"
    assert origin["j1"].job_name == "j1"


def test_execute_sets_default_scheduled_times_and_no_assigned_machine():
    origin = {"j1": JobInfo(job_name="j1", circuit=circuit_with_gate(1), arrival_time=0.0)}
    result = PreSchedulePhase().execute(origin)

    assert result["j1"].scheduled_start_time == 0
    assert result["j1"].scheduled_end_time == 0
    assert result["j1"].assigned_machine is None
