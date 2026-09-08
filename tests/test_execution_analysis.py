from copy import deepcopy
from types import SimpleNamespace

import pytest
from qiskit import QuantumCircuit

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.execution_info import (
    BatchCounts,
    BatchExecutionRecord,
    ExecutionSummary,
    PreparedBatch,
)
from source.component.dataclass.job_info import ExecutionResult, JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.flow.execution.post_execution_analysis import PostExecution
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase


def prepared_batch():
    circuit = QuantumCircuit(3, 3)
    return PreparedBatch(
        job_ids=("canonical_a", "canonical_b"),
        merged_circuit=circuit,
        transpiled_circuit=circuit.copy(),
        classical_bits={"canonical_a": (2, 0), "canonical_b": (1,)},
        logical_qubits=3,
        duration_per_shot=1e-6,
    )


def test_split_counts_uses_explicit_bit_order_and_canonical_ids():
    prepared = prepared_batch()
    counts = BatchCounts({"1 01": 3, "1 10": 1}, {"000": 2, "011": 2})

    split = PostExecution().split_counts(prepared, counts, 4)

    assert list(split) == ["canonical_a", "canonical_b"]
    assert split["canonical_a"] == BatchCounts({"11": 3, "01": 1}, {"00": 2, "10": 2})
    assert split["canonical_b"] == BatchCounts({"0": 3, "1": 1}, {"0": 2, "1": 2})
    assert all(sum(result.distribution_no_noise.values()) == 4 for result in split.values())
    assert all(sum(result.distribution_with_noise.values()) == 4 for result in split.values())
    assert counts.distribution_no_noise == {"1 01": 3, "1 10": 1}


@pytest.mark.parametrize("invalid", [
    {}, None, {"000": 3}, {"000": 5}, {"000": -1, "111": 5},
    {"000": 4.0}, {"000": True, "111": 3}, {"0x0": 4},
    {"00": 4}, {"0000": 4}, {0: 4}, {"0\t00": 4},
])
@pytest.mark.parametrize("field", ["distribution_no_noise", "distribution_with_noise"])
def test_split_counts_rejects_invalid_complete_batch_atomically(invalid, field):
    counts = BatchCounts({"000": 4}, {"111": 4})
    setattr(counts, field, invalid)
    before = deepcopy(counts)

    with pytest.raises(ValueError):
        PostExecution().split_counts(prepared_batch(), counts, 4)

    assert counts == before


@pytest.mark.parametrize("mapping", [
    {}, {"canonical_a": (0, 1), "unknown": (2,)},
    {"canonical_a": (0, 1), "canonical_b": (1,)},
    {"canonical_a": (0,), "canonical_b": (1,)},
    {"canonical_a": (0, 1), "canonical_b": (3,)},
    {"canonical_a": (), "canonical_b": (0, 1, 2)},
    {"canonical_a": (False, 1), "canonical_b": (2,)},
])
def test_split_counts_rejects_missing_overlapping_or_invalid_mapping(mapping):
    prepared = prepared_batch()
    prepared.classical_bits = mapping

    with pytest.raises(ValueError):
        PostExecution().split_counts(prepared, BatchCounts({"000": 4}, {"000": 4}), 4)


def test_split_counts_rejects_transpiled_classical_width_changes():
    prepared = prepared_batch()
    prepared.transpiled_circuit = QuantumCircuit(3, 4)

    with pytest.raises(ValueError, match="classical widths"):
        PostExecution().split_counts(prepared, BatchCounts({"000": 4}, {"000": 4}), 4)


def analysis_example():
    machines = {
        name: MachineCharacteristic(name, object(), capacity)
        for name, capacity in [("first", 4), ("second", 2), ("idle", 4)]
    }
    results = {
        "a": ExecutionResult(
            JobInfo(job_name="not_a", arrival_time=0), "first",
            {"0": 4}, {"1": 4}, start_time=2, end_time=8,
            execution_time=4, status="SUCCEEDED", requested_shots=4, completed_shots=4,
        ),
        "b": ExecutionResult(
            JobInfo(arrival_time=1), "second", {"0": 2}, {"0": 2},
            start_time=1, end_time=3, execution_time=2, status="SUCCEEDED",
            requested_shots=2, completed_shots=2,
        ),
        "failed": ExecutionResult(
            JobInfo(), "first", {"0": 1}, {"0": 1}, fidelity=1.0,
            start_time=8, end_time=10, execution_time=2, status="FAILED",
        ),
        "blocked": ExecutionResult(JobInfo(), "first", status="BLOCKED"),
    }
    summary = ExecutionSummary(makespan=10, batches=[
        BatchExecutionRecord(0, "first", ("a",), 2, 2, 4, 2, "SUCCEEDED"),
        BatchExecutionRecord(1, "second", ("b",), 2, 1, 3, 1, "SUCCEEDED"),
        BatchExecutionRecord(2, "first", ("a",), 2, 6, 8, 2, "SUCCEEDED"),
        BatchExecutionRecord(3, "first", ("failed",), 2, 8, 10, 1, "FAILED"),
    ])
    return machines, results, summary


def test_finalize_uses_successes_for_job_metrics_and_all_batches_for_utilization():
    machines, results, summary = analysis_example()
    capture = ResultOfSchedule(nameSchedule="FFD", ScheduleLatency=0.125)

    PostExecution().finalize(machines, results, summary, capture_result_schedule=capture)

    assert (summary.succeeded_jobs, summary.failed_jobs, summary.blocked_jobs) == (2, 1, 1)
    assert summary.total_turnaround_time == 10
    assert summary.total_waiting_time == 4
    assert summary.total_response_time == 2
    assert summary.average_turnaround_time == 5
    assert summary.average_waiting_time == 2
    assert summary.average_response_time == 1
    assert summary.job_completion_rate == 0.2
    assert summary.average_fidelity == pytest.approx(0.5)
    assert results["failed"].fidelity is None
    assert results["blocked"].fidelity is None
    assert summary.machines["first"].busy_time == 6
    assert summary.machines["first"].qubit_time == 10
    assert summary.machines["first"].utilization == 0.25
    assert summary.machines["second"].utilization == 0.1
    assert summary.machines["idle"].utilization == 0
    assert capture.execution_summary is summary
    assert capture.ScheduleLatency == 0.125


def test_finalize_accepts_generic_capture_and_resets_metrics_when_reused():
    machines, results, summary = analysis_example()
    capture = SimpleNamespace()
    analysis = PostExecution()
    analysis.finalize(machines, results, summary, capture_result_schedule=capture)
    assert capture.execution_summary is summary
    assert capture.execution_summary.average_fidelity == pytest.approx(0.5)
    assert capture.execution_summary.job_completion_rate == 0.2
    assert capture.execution_summary.succeeded_jobs == 2

    summary.makespan = 0
    summary.batches = []
    analysis.finalize(machines, {}, summary, capture_result_schedule=capture)

    assert summary.total_turnaround_time == summary.average_waiting_time == 0
    assert summary.succeeded_jobs == summary.failed_jobs == summary.blocked_jobs == 0
    assert summary.job_completion_rate == summary.average_fidelity == 0
    assert all(machine.utilization == machine.busy_time == 0 for machine in summary.machines.values())
    assert capture.execution_summary.makespan == 0
    assert capture.execution_summary.average_fidelity == capture.execution_summary.succeeded_jobs == 0


@pytest.mark.parametrize("capture_factory", [ResultOfSchedule, SimpleNamespace])
def test_capture_shares_metrics_without_stale_copies_and_can_attach_a_new_report(capture_factory):
    capture = capture_factory()
    analysis = PostExecution()
    summary = ExecutionSummary()
    analysis.finalize({}, {}, summary, capture_result_schedule=capture)

    summary.makespan = 3
    summary.succeeded_jobs = 2
    assert capture.execution_summary is summary
    assert capture.execution_summary.makespan == 3
    assert capture.execution_summary.succeeded_jobs == 2
    assert not hasattr(capture, "makespan")
    assert not hasattr(capture, "succeededJobs")

    replacement = ExecutionSummary()
    analysis.finalize({}, {}, replacement, capture_result_schedule=capture)
    assert capture.execution_summary is replacement
    assert capture.execution_summary.makespan == capture.execution_summary.succeeded_jobs == 0
    assert summary.makespan == 3
    assert summary.succeeded_jobs == 2


def test_schedule_capture_does_not_require_execution_timestamps():
    circuit = QuantumCircuit(1)
    circuit.x(0)
    input_job = {"canonical": JobInfo(job_name="display", circuit=circuit, shots=2)}
    machines = {"m": MachineCharacteristic("display_m", object(), 2)}
    capture = ResultOfSchedule()

    scheduled = ConcreteSchedulePhase(FFD()).execute(input_job, machines, capture)

    assert capture.nameSchedule == "FFD"
    assert capture.ScheduleLatency >= 0
    assert capture.execution_summary is None
    assert scheduled["canonical"].assigned_machine == "m"
    assert not hasattr(scheduled["canonical"], "scheduled_end_time")


def test_real_schedule_execution_updates_capture_after_all_shots_complete():
    from qiskit_ibm_runtime.fake_provider import FakeBelemV2
    from source.flow.execution.phase_execution import ConcreteExecutionPhase

    first = QuantumCircuit(1, 1)
    first.x(0)
    first.measure(0, 0)
    second = QuantumCircuit(1, 1)
    second.measure(0, 0)
    jobs = {
        "first_key": JobInfo(job_name="other_first_name", circuit=first, shots=4),
        "second_key": JobInfo(circuit=second, shots=8),
    }
    machines = {"machine_key": MachineCharacteristic("other_machine_name", FakeBelemV2(), 2)}
    capture = ResultOfSchedule()
    scheduled = ConcreteSchedulePhase(FFD()).execute(jobs, machines, capture)
    execution = ConcreteExecutionPhase()

    results = execution.execute(machines, scheduled, capture, seed=7, gantt_output_path=None)

    assert set(results) == set(jobs)
    assert all(result.status == "SUCCEEDED" for result in results.values())
    assert results["first_key"].distribution_no_noise == {"1": 4}
    assert results["second_key"].distribution_no_noise == {"0": 8}
    assert sum(results["first_key"].distribution_with_noise.values()) == 4
    assert sum(results["second_key"].distribution_with_noise.values()) == 8
    assert [batch.job_ids for batch in execution.execution_summary.batches] == [
        ("first_key", "second_key"), ("second_key",),
    ]
    assert capture.execution_summary is execution.execution_summary
    assert capture.execution_summary.succeeded_jobs == 2
    assert capture.execution_summary.failed_jobs == capture.execution_summary.blocked_jobs == 0
    assert capture.execution_summary.makespan > 0
    assert 0 <= capture.execution_summary.average_fidelity <= 1
    assert jobs["first_key"].circuit == first
    assert first.num_qubits == first.num_clbits == 1


def test_gantt_preserves_batch_boundaries_canonical_ids_and_microsecond_scale(tmp_path, monkeypatch):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib import pyplot as plt

    machines, results, summary = analysis_example()
    for result in results.values():
        for attribute in ["start_time", "end_time", "execution_time"]:
            if getattr(result, attribute) is not None:
                setattr(result, attribute, getattr(result, attribute) * 1e-6)
        result.job_info.arrival_time = (result.job_info.arrival_time or 0) * 1e-6
    for batch in summary.batches:
        batch.start_time *= 1e-6
        batch.end_time *= 1e-6
    summary.makespan *= 1e-6
    observed = {}
    original_savefig = Figure.savefig

    def inspect_and_save(figure, path, **kwargs):
        axis = figure.axes[0]
        observed["limits"] = axis.get_xlim()
        observed["labels"] = [label.get_text() for label in axis.get_yticklabels()]
        observed["annotations"] = [label.get_text() for label in axis.texts]
        observed["bars"] = len(axis.patches)
        observed["boundaries"] = len(axis.collections)
        observed["xlabel"] = axis.get_xlabel()
        original_savefig(figure, path, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_and_save)
    output = tmp_path / "execution.png"

    PostExecution().finalize(machines, results, summary, gantt_output_path=str(output))

    assert output.stat().st_size > 0
    assert 0 < observed["limits"][1] < 20e-6
    assert observed["bars"] == observed["boundaries"] == 4
    assert "first / a [SUCCEEDED]" in observed["labels"]
    assert all("not_a" not in label for label in observed["labels"])
    assert any("B3" in label and "FAILED" in label for label in observed["annotations"])
    assert "seconds" in observed["xlabel"]
    assert not plt.get_fignums()


def test_finalize_does_not_draw_when_no_output_is_requested(monkeypatch):
    def unexpected_draw(*args):
        pytest.fail("Chart drawing was not requested")

    monkeypatch.setattr(PostExecution, "_draw_gantt_chart", unexpected_draw)
    PostExecution().finalize({}, {}, ExecutionSummary())
