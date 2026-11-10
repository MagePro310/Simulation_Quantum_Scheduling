"""Tests for splitting one job's shots across machines and merging the results."""

import pytest
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit.primitives.containers import BitArray, DataBin, PrimitiveResult, PubResult

from source.flow.execution import SilentTimelineReporter
from source.flow.execution.batch_executor import BatchExecutor
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.execution.shot_merger import merge_counts, merge_primitive_results
from source.flow.schedule.cutting import SchedulingCutterHelper
from source.flow.schedule.schedule_phase import SchedulePhase
from source.flow.schedule.shots import ShotDistributionHelper
from source.models.execution import BatchExecutionRecord
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.schedule_result import ResultOfSchedule
from source.simulator import FakeBelemV2, FakeBogotaV2


def _ghz(name: str, qubits: int, shots: int = 1024) -> JobInfo:
    circuit = get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=qubits)
    return JobInfo(job_name=name, circuit=circuit, num_qubits=qubits, shots=shots, arrival_time=0)


def _machines() -> dict[str, MachineCharacteristic]:
    return {
        "belem": MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }


def _assign(jobs: dict[str, SchedulerJobInfo], placement: dict[str, str]) -> dict[str, SchedulerJobInfo]:
    for order, (name, machine) in enumerate(placement.items()):
        jobs[name].assigned_machine = machine
        jobs[name].dispatch_order = order
    return jobs


def _run(scheduler_job, machines, batch_executor=None, seed=0, capture=None):
    reporter = SilentTimelineReporter()
    if batch_executor is not None:
        batch_executor.reporter = reporter
    phase = ExecutionPhase(batch_executor=batch_executor, reporter=reporter)
    results = phase.execute(machines, scheduler_job, seed=seed, capture_result_schedule=capture)
    return results, phase.execution_summary


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def test_split_shots_evenly_preserves_total_and_links_shards():
    job = _ghz("j", 3, shots=1025)
    shards = ShotDistributionHelper.split_shots(job, 2)

    assert list(shards) == ["j_shot0", "j_shot1"]
    assert [s.job_information.shots for s in shards.values()] == [513, 512]
    for shard in shards.values():
        info = shard.job_information
        assert info.shot_parent is job
        assert info.circuit is job.circuit
        assert info.parent_job is None
        assert shard.assigned_machine is None
    assert set(job.shot_shards) == set(shards)


def test_split_shots_explicit_shares_and_inherited_dependencies():
    dep = _ghz("dep", 2)
    job = SchedulerJobInfo(job_information=_ghz("j", 3, shots=1000), depends_on=[dep])
    shards = ShotDistributionHelper.split_shots(job, [700, 300])

    assert [s.job_information.shots for s in shards.values()] == [700, 300]
    assert all(s.depends_on == [dep] for s in shards.values())


@pytest.mark.parametrize("shares", [[500, 400], [1024], [0, 1024], 1, 2000])
def test_split_shots_rejects_invalid_shares(shares):
    with pytest.raises(ValueError):
        ShotDistributionHelper.split_shots(_ghz("j", 3, shots=1024), shares)


def test_shards_cannot_be_split_again_or_cut():
    job = _ghz("j", 4)
    shard = next(iter(ShotDistributionHelper.split_shots(job, 2).values()))

    assert not ShotDistributionHelper.can_split(shard)
    assert not ShotDistributionHelper.can_split(job)  # already split
    assert not SchedulingCutterHelper.can_cut(shard)
    assert not SchedulingCutterHelper.can_cut(job)
    with pytest.raises(ValueError):
        ShotDistributionHelper.split_shots(shard, 2)


def test_cut_subcircuit_shards_keep_subexperiments():
    sub = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    sub_a = sub["big_sub_A"].job_information
    shards = ShotDistributionHelper.split_shots(sub["big_sub_A"], 2)

    for shard in shards.values():
        info = shard.job_information
        assert info.subexperiments is sub_a.subexperiments
        assert info.partition_label == "A"
        assert info.shot_parent is sub_a
        assert info.parent_job is None  # only the merged subcircuit counts toward reconstruction


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _primitive(obs: list[str], qpd: list[str]) -> PrimitiveResult:
    data = DataBin(
        observable_measurements=BitArray.from_samples(obs, num_bits=2),
        qpd_measurements=BitArray.from_samples(qpd, num_bits=1),
    )
    return PrimitiveResult([PubResult(data), PubResult(data)])


def test_merge_primitive_results_concatenates_shots_per_pub():
    first = _primitive(["00", "11", "11"], ["0", "1", "0"])
    second = _primitive(["01"], ["1"])
    merged = merge_primitive_results([None, first, second])

    assert len(merged) == 2
    for pub in merged:
        assert pub.data.observable_measurements.num_shots == 4
        assert pub.data.qpd_measurements.num_shots == 4
        assert pub.data.observable_measurements.get_counts() == {"00": 1, "11": 2, "01": 1}
    assert merge_primitive_results([None, first]) is first
    assert merge_primitive_results([None, None]) is None


def test_merge_counts_adds_distributions():
    assert merge_counts({"0": 3}, None, {"0": 1, "1": 2}) == {"0": 4, "1": 2}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def test_uncut_job_split_across_two_machines_merges_into_one_result():
    shards = ShotDistributionHelper.split_shots(_ghz("j", 3), [512, 512])
    scheduler_job = _assign(shards, {"j_shot0": "belem", "j_shot1": "bogota"})

    results, summary = _run(scheduler_job, _machines())

    merged = results["j"]
    assert merged.status == "SUCCEEDED"
    assert merged.completed_shots == 1024
    assert sum(merged.distribution_with_noise.values()) == 1024
    assert sum(merged.distribution_no_noise.values()) == 1024
    assert 0.0 <= merged.fidelity <= 1.0
    assert {b.machine_name for b in summary.batches} == {"belem", "bogota"}
    # Shards ran in parallel, so the merged busy time is one shard's, not their sum
    assert merged.execution_time == pytest.approx(max(results[n].execution_time for n in shards))
    assert (summary.succeeded_jobs, summary.failed_jobs, summary.blocked_jobs) == (1, 0, 0)


def test_cut_subcircuit_split_across_machines_reconstructs_parent():
    sub = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    sub_a_info = sub["big_sub_A"].job_information
    scheduler_job = {"big_sub_B": sub["big_sub_B"], **ShotDistributionHelper.split_shots(sub["big_sub_A"], 2)}
    scheduler_job = _assign(
        scheduler_job,
        {"big_sub_A_shot0": "belem", "big_sub_A_shot1": "bogota", "big_sub_B": "bogota"},
    )

    results, summary = _run(scheduler_job, _machines())

    assert results["big_sub_A"].status == "SUCCEEDED"
    assert results["big"].status == "SUCCEEDED"
    assert results["big"].reconstructed_distribution
    assert 0.0 <= results["big"].fidelity <= 1.0
    # Reconstruction used every shot of the split subcircuit, not one shard's
    merged_a = sub_a_info.parent_job.cutting_context.sub_results["A"]
    assert all(pub.data.observable_measurements.num_shots == 1024 for pub in merged_a)
    assert (summary.succeeded_jobs, summary.failed_jobs, summary.blocked_jobs) == (1, 0, 0)


def test_dependency_on_split_job_waits_for_every_shard():
    shards = ShotDistributionHelper.split_shots(_ghz("j", 3), [512, 512])
    later = SchedulerJobInfo(job_information=_ghz("later", 2), depends_on=[shards["j_shot0"].job_information.shot_parent])
    scheduler_job = _assign({**shards, "later": later}, {"j_shot0": "belem", "j_shot1": "bogota", "later": "belem"})

    results, summary = _run(scheduler_job, _machines())

    assert results["later"].status == "SUCCEEDED"
    assert results["later"].start_time >= results["j"].end_time
    assert summary.succeeded_jobs == 2


def test_same_seed_gives_identical_merged_fidelity():
    def fidelity():
        shards = ShotDistributionHelper.split_shots(_ghz("j", 3), 2)
        results, _ = _run(_assign(shards, {"j_shot0": "belem", "j_shot1": "bogota"}), _machines(), seed=7)
        return results["j"].fidelity

    assert fidelity() == fidelity()


class _FailOnMachine(BatchExecutor):
    """Batch executor that fails every batch on one machine."""

    def __init__(self, machine_name: str):
        super().__init__()
        self.machine_name = machine_name

    def execute_batch(self, now, machine, active_jobs, scheduler_job, results, prepared_batch, seed, batch_id):
        if machine.name != self.machine_name:
            return super().execute_batch(now, machine, active_jobs, scheduler_job, results, prepared_batch, seed, batch_id)
        record = BatchExecutionRecord(
            batch_id=batch_id,
            machine_name=machine.name,
            job_ids=tuple(active_jobs),
            shots=0,
            start_time=now,
            end_time=now,
            logical_qubits=0,
        )
        return record, None, "injected failure", None


def test_failed_shard_fails_logical_job_and_cut_parent():
    sub = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    scheduler_job = {"big_sub_B": sub["big_sub_B"], **ShotDistributionHelper.split_shots(sub["big_sub_A"], 2)}
    scheduler_job = _assign(
        scheduler_job,
        {"big_sub_A_shot0": "belem", "big_sub_A_shot1": "bogota", "big_sub_B": "belem"},
    )

    results, summary = _run(scheduler_job, _machines(), batch_executor=_FailOnMachine("bogota"))

    assert results["big_sub_A_shot1"].status == "FAILED"
    assert results["big_sub_A"].status == "FAILED"
    assert results["big"].status == "FAILED"
    assert (summary.succeeded_jobs, summary.failed_jobs, summary.blocked_jobs) == (0, 1, 0)


def test_returning_split_job_together_with_its_shards_is_rejected():
    job = _ghz("j", 3)
    shards = ShotDistributionHelper.split_shots(job, 2)
    scheduler_job = _assign({**shards, "j": SchedulerJobInfo(job_information=job)}, {"j_shot0": "belem", "j_shot1": "bogota", "j": "belem"})

    with pytest.raises(ValueError, match="split into shot shards"):
        _run(scheduler_job, _machines())


def test_missing_shard_is_rejected():
    shards = ShotDistributionHelper.split_shots(_ghz("j", 3), 2)
    scheduler_job = _assign({"j_shot0": shards["j_shot0"]}, {"j_shot0": "belem"})

    with pytest.raises(ValueError, match="missing from the schedule"):
        _run(scheduler_job, _machines())


class _SplitEveryJob:
    """Minimal algorithm: split each job in two and put one shard on each machine."""

    def execute(self, scheduler_job, machines):
        names = list(machines)
        out = {}
        for job in scheduler_job.values():
            for index, (name, shard) in enumerate(ShotDistributionHelper.split_shots(job, len(names)).items()):
                shard.assigned_machine = names[index]
                shard.dispatch_order = len(out)
                out[name] = shard
        return out


def test_schedule_phase_records_shot_distribution():
    capture = ResultOfSchedule()
    machines = _machines()
    scheduled = SchedulePhase(algorithm=_SplitEveryJob()).execute({"j": _ghz("j", 3)}, machines, capture)

    assert capture.shot_distribution is True
    results, summary = _run(scheduled, machines, capture=capture)
    assert results["j"].status == "SUCCEEDED"
    assert summary.succeeded_jobs == 1


def test_subcircuit_running_over_several_batches_keeps_every_shot():
    """A batch runs the smallest remaining shot count, so a subcircuit sharing one
    with a shorter job finishes in a later batch; reconstruction must see both."""
    sub = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    scheduler_job = {
        "big_sub_A": sub["big_sub_A"],
        "big_sub_B": sub["big_sub_B"],
        "short": SchedulerJobInfo(job_information=_ghz("short", 2, shots=256)),
    }
    scheduler_job = _assign(scheduler_job, {"big_sub_A": "belem", "big_sub_B": "bogota", "short": "bogota"})

    results, summary = _run(scheduler_job, _machines())

    assert len([b for b in summary.batches if "big_sub_B" in b.job_ids]) == 2
    assert results["big"].status == "SUCCEEDED"
    sub_b = sub["big_sub_B"].job_information.parent_job.cutting_context.sub_results["B"]
    assert all(pub.data.observable_measurements.num_shots == 1024 for pub in sub_b)


def test_shards_in_joint_batches_draw_independent_ideal_samples():
    """An uncut job batched with a cut subcircuit takes the joint-execution path; its
    ideal baseline must use the batch's seed, or every shard repeats the same samples."""
    first = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    second = SchedulingCutterHelper.cut_job(_ghz("other", 7), cluster_sizes=[5, 2])
    shards = ShotDistributionHelper.split_shots(_ghz("j", 3), 2)
    scheduler_job = _assign(
        {**first, **second, **shards},
        {
            "big_sub_B": "bogota", "j_shot0": "bogota",
            "other_sub_B": "belem", "j_shot1": "belem",
            "big_sub_A": "bogota", "other_sub_A": "belem",
        },
    )

    results, summary = _run(scheduler_job, _machines())

    for shard in ("j_shot0", "j_shot1"):
        batch = next(b for b in summary.batches if shard in b.job_ids)
        assert any("_sub_" in name for name in batch.job_ids)  # ran on the joint path
    assert results["j_shot0"].distribution_no_noise != results["j_shot1"].distribution_no_noise
    assert results["j"].status == "SUCCEEDED"
    assert (summary.succeeded_jobs, summary.failed_jobs) == (3, 0)
