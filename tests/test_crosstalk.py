"""Conditional crosstalk: simultaneous two-qubit gates on neighbouring pairs get extra error."""

import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Kraus, average_gate_fidelity
from qiskit_aer.noise import depolarizing_error

from source.flow.execution import SilentTimelineReporter
from source.flow.execution.circuit_composer import build_pass_manager
from source.flow.execution.crosstalk import (
    apply_crosstalk,
    crosstalk_gate_indices,
    extra_depolarizing_param,
    two_qubit_gate_timeline,
)
from source.flow.execution.orchestrator import ExecutionPhase
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic
from source.models.simulation_config import ExecutionConfig
from source.simulator import FakeBelemV2, FakeBogotaV2


def _machine(backend, factor: float = 2.0) -> MachineCharacteristic:
    return MachineCharacteristic(name=backend.name, quantum_machine=backend, capacity=5, crosstalk_factor=factor)


def _two_cnots(layout: list[int], backend, sequential: bool = False) -> QuantumCircuit:
    """CNOTs on logical (0,1) and (2,3), placed on the given physical qubits and scheduled."""
    circuit = QuantumCircuit(4, 4)
    circuit.h([0, 2])
    circuit.cx(0, 1)
    if sequential:
        circuit.barrier()
    circuit.cx(2, 3)
    circuit.measure(range(4), range(4))
    return build_pass_manager(_machine(backend), seed=1, initial_layout=layout).run(circuit)


def test_timeline_matches_qiskit_schedule():
    backend = FakeBelemV2()
    isa = _two_cnots([0, 1, 3, 4], backend)
    starts = {index: start for index, start, _, _ in two_qubit_gate_timeline(isa, backend)}
    assert starts and all(isa.op_start_times[i] == start for i, start in starts.items())


def test_parallel_cnots_on_neighbouring_pairs_are_exposed():
    belem = FakeBelemV2()  # T shape: (0,1) and (3,4) are linked through 1-3
    exposed, total = crosstalk_gate_indices(_two_cnots([0, 1, 3, 4], belem), belem)
    assert (len(exposed), total) == (2, 2)


def test_distance_on_a_line_device():
    bogota = FakeBogotaV2()  # line 0-1-2-3-4
    far, _ = crosstalk_gate_indices(_two_cnots([0, 1, 3, 4], bogota), bogota)
    near, _ = crosstalk_gate_indices(_two_cnots([0, 1, 2, 3], bogota), bogota)
    assert len(far) == 0
    assert len(near) == 2


def test_sequential_cnots_are_not_exposed():
    belem = FakeBelemV2()
    exposed, total = crosstalk_gate_indices(_two_cnots([0, 1, 3, 4], belem, sequential=True), belem)
    assert (len(exposed), total) == (0, 2)


def test_factor_one_returns_the_input_circuit():
    belem = FakeBelemV2()
    isa = _two_cnots([0, 1, 3, 4], belem)
    circuit, exposed, total = apply_crosstalk(isa, belem, 1.0)
    assert circuit is isa
    assert (exposed, total) == (2, 2)  # exposure is reported even with crosstalk off


def test_channels_follow_exposed_gates():
    belem = FakeBelemV2()
    noisy, exposed, _ = apply_crosstalk(_two_cnots([0, 1, 3, 4], belem), belem, 3.0)
    names = [instruction.operation.name for instruction in noisy.data]
    assert names.count("kraus") == exposed == 2
    for i, name in enumerate(names):
        if name == "kraus":
            assert names[i - 1] == "cx"


@pytest.mark.parametrize("factor", [2.0, 3.0, 5.0])
def test_extra_error_is_factor_minus_one_times_gate_error(factor):
    gate_error = 0.0166
    param = extra_depolarizing_param(gate_error, factor)
    infidelity = 1 - average_gate_fidelity(Kraus(depolarizing_error(param, 2)))
    assert infidelity == pytest.approx((factor - 1) * gate_error)


def test_config_rejects_factor_below_one():
    with pytest.raises(ValueError):
        ExecutionConfig(crosstalk_factor=0.5)
    assert ExecutionConfig.from_dict({"crosstalk_factor": 3}).crosstalk_factor == 3.0


def _bell(name: str) -> JobInfo:
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return JobInfo(job_name=name, circuit=circuit, num_qubits=2, shots=2000, arrival_time=0)


def _run(jobs: dict[str, JobInfo], factor: float):
    machine = _machine(FakeBelemV2(), factor)
    scheduler_job = {}
    for order, (name, info) in enumerate(jobs.items()):
        scheduler_job[name] = SchedulerJobInfo(job_information=info, assigned_machine=machine.name, dispatch_order=order)
    phase = ExecutionPhase(reporter=SilentTimelineReporter())
    results = phase.execute({machine.name: machine}, scheduler_job, seed=4)
    return results, phase.execution_summary


def test_multiprogrammed_batch_loses_fidelity_to_crosstalk():
    jobs = {"a": _bell("a"), "b": _bell("b")}
    _, clean = _run(jobs, 1.0)
    _, noisy = _run(jobs, 5.0)
    assert len(clean.batches) == 1 and len(clean.batches[0].job_ids) == 2
    assert noisy.crosstalk_exposure == clean.crosstalk_exposure > 0
    assert noisy.average_fidelity < clean.average_fidelity


def test_job_alone_without_parallel_cnots_is_unaffected():
    ghz = QuantumCircuit(3, 3)
    ghz.h(0)
    ghz.cx(0, 1)
    ghz.cx(1, 2)
    ghz.measure(range(3), range(3))
    jobs = {"ghz": JobInfo(job_name="ghz", circuit=ghz, num_qubits=3, shots=1000, arrival_time=0)}
    off, off_summary = _run(jobs, 1.0)
    on, on_summary = _run(jobs, 3.0)
    assert on_summary.crosstalk_exposure == 0.0
    assert on["ghz"].distribution_with_noise == off["ghz"].distribution_with_noise
