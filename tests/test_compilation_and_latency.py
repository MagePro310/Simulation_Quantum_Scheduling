"""Both batch paths compile the same way, and scheduling latency is measured the same way
for every algorithm."""

import time

from mqt.bench import BenchmarkLevel, get_benchmark

from source.flow.execution import SilentTimelineReporter
from source.flow.execution.circuit_composer import CircuitPreparation
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.schedule.cutting import SchedulingCutterHelper
from source.flow.schedule.schedule_phase import SchedulePhase
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.schedule_result import ResultOfSchedule
from source.simulator import FakeBelemV2, FakeBogotaV2


def _ghz(name: str, qubits: int) -> JobInfo:
    circuit = get_benchmark("ghz", level=BenchmarkLevel.INDEP, circuit_size=qubits)
    return JobInfo(job_name=name, circuit=circuit, num_qubits=qubits, shots=256, arrival_time=0)


def _belem() -> MachineCharacteristic:
    return MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5)


class RecordingLayout:
    """Records each call and leaves the layout to Qiskit."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    def get_initial_layout(self, backend, jobs):
        self.calls.append(tuple(jobs))
        return None


def test_standard_path_uses_layout_and_alap_schedule():
    prepared = CircuitPreparation().prepare_batch(
        _belem(), {"a": _ghz("a", 2)}, seed=1, initial_layout=[4, 3]
    )
    layout = prepared.transpiled_circuit.layout.initial_virtual_layout(filter_ancillas=True)
    assert [layout[q] for q in prepared.merged_circuit.qubits] == [4, 3]
    assert prepared.transpiled_circuit.op_start_times is not None  # scheduled


def test_layout_strategy_is_called_on_both_paths():
    big = SchedulingCutterHelper.cut_job(_ghz("big", 7), cluster_sizes=[5, 2])
    scheduler_job = {**big, "plain": SchedulerJobInfo(job_information=_ghz("plain", 3))}
    placement = {"plain": "belem", "big_sub_A": "bogota", "big_sub_B": "bogota"}
    for order, (name, machine) in enumerate(placement.items()):
        scheduler_job[name].assigned_machine = machine
        scheduler_job[name].dispatch_order = order
    machines = {
        "belem": _belem(),
        "bogota": MachineCharacteristic(name="bogota", quantum_machine=FakeBogotaV2(), capacity=5),
    }

    layout = RecordingLayout()
    phase = ExecutionPhase(layout_strategy=layout, reporter=SilentTimelineReporter())
    results = phase.execute(machines, scheduler_job, seed=0)

    assert ("plain",) in layout.calls           # standard path
    assert ("big_sub_A",) in layout.calls       # joint path
    assert results["big"].status == "SUCCEEDED"


class CuttingAlgorithm:
    """Cuts one job (made slow on purpose), prints, and assigns everything to one machine."""

    def execute(self, scheduler_job, machines):
        print("noisy algorithm output")
        jobs = dict(scheduler_job)
        jobs.update(SchedulingCutterHelper.cut_job(jobs.pop("wide"), cluster_sizes=[2, 2]))
        for order, s_job in enumerate(jobs.values()):
            s_job.assigned_machine = "belem"
            s_job.dispatch_order = order
        return jobs


def test_latency_excludes_subexperiment_generation(monkeypatch, capsys):
    cutter = SchedulingCutterHelper._cutter
    original = cutter.cut_by_partition_sizes

    def slow_cut(*args, **kwargs):
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(cutter, "cut_by_partition_sizes", slow_cut)
    capture = ResultOfSchedule()
    SchedulePhase(algorithm=CuttingAlgorithm()).execute(
        {"wide": _ghz("wide", 4), "small": _ghz("small", 2)}, {"belem": _belem()}, capture
    )

    assert capture.cutting_time >= 0.3
    assert capture.schedule_latency < 0.3
    assert "noisy algorithm output" in capsys.readouterr().out  # held back, then printed
