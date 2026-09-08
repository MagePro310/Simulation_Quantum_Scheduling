from types import SimpleNamespace

import pytest
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit import Parameter
from qiskit.result import marginal_counts
from qiskit_ibm_runtime.fake_provider import FakeBelemV2

from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.execution.main_execution_quantum import MainExecutionQuantum
from source.flow.execution.pre_execution_transpile import PreExecution


@pytest.fixture
def machine():
    backend = FakeBelemV2()
    return MachineCharacteristic(backend.name, backend, backend.num_qubits)


def make_job(circuit, name="display_name"):
    return JobInfo(job_name=name, circuit=circuit, num_qubits=circuit.num_qubits, shots=256)


def test_partial_measurement_and_multiple_registers_preserve_exact_bit_mapping(machine):
    first = QuantumCircuit(2, 1)
    first.x(1)
    first.measure(1, 0)
    second = QuantumCircuit(
        QuantumRegister(2, "data"), ClassicalRegister(1, "left"), ClassicalRegister(2, "right")
    )
    second.x(0)
    second.measure(0, 0)
    second.measure(1, 2)
    originals = [first.copy(), second.copy()]
    # The logical admission limit may be smaller than the full physical target.
    machine.capacity = 4
    jobs = {"canonical_first": make_job(first), "canonical_second": make_job(second)}

    prepared = PreExecution().prepare_batch(machine, jobs, seed=17)
    counts = MainExecutionQuantum().execute_batch(machine, prepared, 128, seed=23)

    assert prepared.job_ids == ("canonical_first", "canonical_second")
    assert prepared.classical_bits == {"canonical_first": (0,), "canonical_second": (1, 2, 3)}
    assert prepared.logical_qubits == prepared.merged_circuit.num_qubits == 4
    assert prepared.transpiled_circuit.num_qubits == machine.quantum_machine.num_qubits == 5
    assert prepared.merged_circuit.num_clbits == 4
    assert [register.name for register in prepared.merged_circuit.cregs] == ["meas"]
    assert counts.distribution_no_noise == {"0011": 128}
    assert marginal_counts(counts.distribution_no_noise, prepared.classical_bits["canonical_first"]) == {"1": 128}
    assert marginal_counts(counts.distribution_no_noise, prepared.classical_bits["canonical_second"]) == {"001": 128}
    assert sum(counts.distribution_with_noise.values()) == 128
    assert first == originals[0]
    assert second == originals[1]
    assert jobs["canonical_first"].circuit is first
    assert jobs["canonical_second"].circuit is second
    assert [register.name for register in second.cregs] == ["left", "right"]


def test_real_local_simulation_has_reproducible_counts_and_seconds_duration(machine):
    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    jobs = {"bell": make_job(circuit)}
    prepared = PreExecution().prepare_batch(machine, jobs, seed=41)
    repeated = PreExecution().prepare_batch(machine, jobs, seed=41)
    executor = MainExecutionQuantum()

    counts = executor.execute_batch(machine, prepared, 256, seed=73)
    repeated_counts = executor.execute_batch(machine, repeated, 256, seed=73)

    assert counts == repeated_counts
    assert prepared.transpiled_circuit == repeated.transpiled_circuit
    assert sum(counts.distribution_no_noise.values()) == 256
    assert sum(counts.distribution_with_noise.values()) == 256
    assert set(counts.distribution_no_noise) == {"00", "11"}
    assert 0 < prepared.duration_per_shot < 0.001
    with pytest.warns(DeprecationWarning):
        duration_in_seconds = prepared.transpiled_circuit.duration * machine.quantum_machine.dt
    assert prepared.duration_per_shot == pytest.approx(duration_in_seconds)
    assert executor.max_shots(machine) == 8192


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
def test_prepare_rejects_unusable_target_duration(machine, monkeypatch, duration):
    circuit = QuantumCircuit(1, 1)
    circuit.measure(0, 0)
    monkeypatch.setattr(QuantumCircuit, "estimate_duration", lambda *args, **kwargs: duration)

    with pytest.raises(ValueError, match="invalid per-shot duration"):
        PreExecution().prepare_batch(machine, {"job": make_job(circuit)}, seed=1)


def test_prepare_rejects_empty_or_oversized_batches(machine):
    with pytest.raises(ValueError, match="At least one job"):
        PreExecution().prepare_batch(machine, {}, seed=1)

    circuit = QuantumCircuit(3, 3)
    circuit.measure(range(3), range(3))
    with pytest.raises(ValueError, match="requires 6 logical qubits"):
        PreExecution().prepare_batch(
            machine, {"a": make_job(circuit), "b": make_job(circuit)}, seed=1
        )


def test_prepare_rejects_unmeasured_and_unbound_circuits(machine):
    unmeasured = QuantumCircuit(1, 1)
    with pytest.raises(ValueError, match="requires a measured circuit"):
        PreExecution().prepare_batch(machine, {"job": make_job(unmeasured)}, seed=1)

    unbound = QuantumCircuit(1, 1)
    unbound.rx(Parameter("theta"), 0)
    unbound.measure(0, 0)
    with pytest.raises(ValueError, match="unbound circuit parameters"):
        PreExecution().prepare_batch(machine, {"job": make_job(unbound)}, seed=1)


@pytest.mark.parametrize("shots", [0, -1, True, 1.5])
def test_execute_rejects_invalid_shot_requests_before_submission(machine, shots):
    with pytest.raises(ValueError, match="positive integer"):
        MainExecutionQuantum().execute_batch(machine, None, shots, seed=1)


def test_execute_enforces_machine_limit_before_submission(machine):
    with pytest.raises(ValueError, match="limit of 8192"):
        MainExecutionQuantum().execute_batch(machine, None, 8193, seed=1)


def test_max_shots_uses_limits_not_default_options():
    backend = SimpleNamespace(
        max_shots=200,
        configuration=lambda: {"max_shots": 150},
        options=SimpleNamespace(shots=8, max_shot_size=4, validator={"shots": (1, 100)}),
    )
    machine = MachineCharacteristic("limited", backend, 1)
    assert MainExecutionQuantum.max_shots(machine) == 100

    backend = SimpleNamespace(options=SimpleNamespace(shots=8, max_shot_size=4))
    machine = MachineCharacteristic("unlimited", backend, 1)
    assert MainExecutionQuantum.max_shots(machine) is None
