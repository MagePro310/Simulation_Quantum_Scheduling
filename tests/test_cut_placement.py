"""Cut placement picks the cheapest qubits for each subcircuit; the cut budget refuses
cuts that would need too many subexperiments."""

import pytest
from qiskit import QuantumCircuit

from source.flow.input.benchmark_circuits import load_benchmark_circuit
from source.flow.runner import run_pipeline
from source.flow.schedule.cutting import CutBudgetExceeded, SchedulingCutterHelper, plan_cut
from source.flow.schedule.cutting import cut_placement
from source.flow.schedule.cutting.cutter_pipeline import CircuitCutter
from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.simulation_config import ExecutionConfig, SchedulingConfig, SimulationConfig, WorkloadConfig


def _clean(benchmark: str, qubits: int) -> QuantumCircuit:
    return load_benchmark_circuit(benchmark, qubits).remove_final_measurements(inplace=False)


def _job(benchmark: str, qubits: int, name: str = "j") -> JobInfo:
    circuit = load_benchmark_circuit(benchmark, qubits)
    return JobInfo(job_name=name, circuit=circuit, num_qubits=circuit.num_qubits, shots=512, arrival_time=0)


@pytest.fixture(autouse=True)
def _restore_budget():
    budget = SchedulingCutterHelper.max_subexperiments
    yield
    SchedulingCutterHelper.max_subexperiments = budget


def test_deutsch_jozsa_cuts_one_gate_instead_of_five():
    contiguous = [0, 0, 0, 0, 0, 1]
    plan = plan_cut(_clean("dj", 6), [5, 1])
    assert list(plan.labels) != contiguous
    assert (plan.num_cuts, plan.overhead, plan.num_subexperiments) == (1, pytest.approx(9.0), 6)


def test_qpe_picks_the_cheapest_phase_gates():
    assert plan_cut(_clean("qpeexact", 6), [5, 1]).overhead == pytest.approx(50.2, rel=0.01)


def test_ghz_keeps_the_contiguous_assignment():
    plan = plan_cut(_clean("ghz", 7), [5, 2])
    assert plan.labels == (0, 0, 0, 0, 0, 1, 1)
    assert (plan.num_cuts, plan.overhead) == (1, pytest.approx(9.0))


@pytest.mark.parametrize(("benchmark", "qubits", "sizes"), [("dj", 6, [3, 3]), ("qpeexact", 6, [4, 2]), ("wstate", 7, [3, 4])])
def test_local_search_matches_enumeration_on_small_circuits(monkeypatch, benchmark, qubits, sizes):
    exact = plan_cut(_clean(benchmark, qubits), sizes)
    monkeypatch.setattr(cut_placement, "MAX_ENUMERATED_ASSIGNMENTS", 0)
    searched = plan_cut(_clean(benchmark, qubits), sizes)
    assert searched.overhead == pytest.approx(exact.overhead)


def test_plan_matches_the_actual_cut():
    job = _job("dj", 6)
    plan = SchedulingCutterHelper.estimate_cut(job, [5, 1])
    children = CircuitCutter().cut_by_partition_sizes(job, [5, 1])
    assert job.cutting_overhead == pytest.approx(plan.overhead)
    assert sorted(child.num_qubits for child in children.values()) == [1, 5]
    for child in children.values():
        assert len(child.subexperiments) == plan.num_subexperiments


def test_budget_refuses_a_dense_cut_before_generating_anything():
    SchedulingCutterHelper.max_subexperiments = 216
    with pytest.raises(CutBudgetExceeded, match="7776 subexperiments"):
        SchedulingCutterHelper.cut_job(_job("qft", 6), cluster_sizes=[5, 1])


def test_optional_cut_over_budget_leaves_the_job_whole():
    SchedulingCutterHelper.max_subexperiments = 216
    jobs = {"q": SchedulerJobInfo(job_information=_job("qft", 5, "q"))}
    assert set(SchedulingCutterHelper.cut_jobs(jobs, target_qubits=3)) == {"q"}


def test_preschedule_rejects_an_oversized_uncuttable_job():
    SchedulingCutterHelper.max_subexperiments = 216
    pre = PreSchedulePhase()
    scheduled = pre.execute_mandatory_cut({"q": _job("qft", 6, "q"), "g": _job("ghz", 7, "g")}, max_capacity=5)
    assert set(pre.rejected) == {"q"}
    assert "uncuttable" in pre.rejected["q"][1]
    assert set(scheduled) == {"g_sub_A", "g_sub_B"}


def test_rejected_job_fails_and_the_rest_still_run():
    config = SimulationConfig(
        workload=WorkloadConfig(
            benchmark="qft",
            jobs={"small": {"qubits": 3, "shots": 256}, "big": {"qubits": 6, "shots": 256}},
        ),
        machines=["FakeBelemV2", "FakeBogotaV2"],
        scheduling=SchedulingConfig(max_subexperiments=216),
        execution=ExecutionConfig(seed=1),
    )
    result = run_pipeline("FFD", config=config)
    summary = result["execution_summary"]
    assert (summary["succeeded_jobs"], summary["failed_jobs"], summary["rejected_jobs"]) == (1, 1, 1)
    assert set(result["rejected"]) == {"big"}


def test_cut_deutsch_jozsa_reconstructs_with_good_fidelity():
    config = SimulationConfig(
        workload=WorkloadConfig(benchmark="dj", jobs={"dj": {"qubits": 6, "shots": 1024}}),
        machines=["FakeBelemV2"],
        execution=ExecutionConfig(seed=2, crosstalk_factor=1.0),
    )
    summary = run_pipeline("FFD", config=config)["execution_summary"]
    assert summary["succeeded_jobs"] == 1
    assert summary["total_cutting_overhead"] == pytest.approx(9.0)
    assert summary["average_fidelity"] > 0.5


def test_config_parses_the_budget():
    assert SchedulingConfig.from_dict({"max_subexperiments": 36}).max_subexperiments == 36
    with pytest.raises(ValueError):
        SchedulingConfig(max_subexperiments=0)
