"""Exact noiseless output distributions, the reference every fidelity is measured against.

A sampled ideal reference carries its own shot noise: a 1024-shot ideal sample of a
GHZ-3 circuit has fidelity about 0.9998 against the exact distribution, and less for
circuits whose output spreads over many bitstrings. The reference is therefore
computed from the statevector, and returned as expected counts (probability x shots),
so it adds up over batches and shot shards the same way sampled counts do.

Keys follow Qiskit's count convention: one character per classical bit, clbit 0
rightmost, no register separators.
"""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator

_SKIPPED = {"barrier", "delay"}
_PROBABILITY_CUTOFF = 1e-12


class UnsupportedIdealCircuit(ValueError):
    """The circuit has operations a statevector cannot represent exactly."""


def measurement_map(circuit: QuantumCircuit) -> tuple[dict[int, int], int]:
    """(clbit -> measured qubit, number of clbits) of a circuit whose measurements are terminal.

    A circuit without classical bits counts as measured on every qubit, clbit i <- qubit i.

    Raises:
        UnsupportedIdealCircuit: For resets, classically controlled operations, a gate
            after a measurement on the same qubit, or a classical bit written twice.
    """
    if circuit.num_clbits == 0:
        return {q: q for q in range(circuit.num_qubits)}, circuit.num_qubits
    clbit_source: dict[int, int] = {}
    measured_qubits: set[int] = set()
    for instruction in circuit.data:
        operation = instruction.operation
        qubits = [circuit.find_bit(q).index for q in instruction.qubits]
        if operation.name in _SKIPPED:
            continue
        if operation.name == "measure":
            clbit = circuit.find_bit(instruction.clbits[0]).index
            if clbit in clbit_source:
                raise UnsupportedIdealCircuit(f"classical bit {clbit} is written twice")
            clbit_source[clbit] = qubits[0]
            measured_qubits.add(qubits[0])
            continue
        if instruction.clbits or operation.name == "reset":
            raise UnsupportedIdealCircuit(f"non-unitary operation {operation.name!r}")
        if measured_qubits.intersection(qubits):
            raise UnsupportedIdealCircuit(f"{operation.name!r} acts on a measured qubit")
    return clbit_source, circuit.num_clbits


def _unitary_part(circuit: QuantumCircuit) -> QuantumCircuit:
    unitary = QuantumCircuit(circuit.num_qubits)
    for instruction in circuit.data:
        if instruction.operation.name in _SKIPPED or instruction.operation.name == "measure":
            continue
        unitary.append(instruction.operation, [circuit.find_bit(q).index for q in instruction.qubits])
    return unitary


def project_to_clbits(
    dist_by_qubit: dict[str, float],
    num_qubits: int,
    clbit_map: dict[int, int],
    width: int,
) -> dict[str, float]:
    """Re-key a distribution over all qubits onto a circuit's own classical bits.

    Input keys are qubit-ordered (Qiskit convention, qubit 0 rightmost). Output keys
    have one character per clbit (clbit 0 rightmost): clbit c holds the bit of the
    qubit measured into it, unmeasured clbits read "0". Keys that collapse together
    (unmeasured qubits) are summed, giving the marginal distribution.
    """
    projected: dict[str, float] = {}
    for key, value in dist_by_qubit.items():
        bits = ["0"] * width
        for clbit, qubit in clbit_map.items():
            bits[width - 1 - clbit] = key[num_qubits - 1 - qubit]
        new_key = "".join(bits)
        projected[new_key] = projected.get(new_key, 0.0) + value
    return projected


def ideal_probabilities(circuit: QuantumCircuit) -> dict[str, float]:
    """Exact output distribution of a circuit whose measurements are all terminal.

    A circuit without classical bits is measured on every qubit, as measure_all() would.

    Raises:
        UnsupportedIdealCircuit: For resets, classically controlled operations,
            a gate after a measurement on the same qubit, or a classical bit
            written twice.
    """
    clbit_source, width = measurement_map(circuit)
    order = sorted(set(clbit_source.values()))
    position = {qubit: bit for bit, qubit in enumerate(order)}
    probabilities = Statevector(_unitary_part(circuit)).probabilities(qargs=order)

    distribution: dict[str, float] = {}
    for outcome, probability in enumerate(probabilities):
        if probability < _PROBABILITY_CUTOFF:
            continue
        bits = ["0"] * width
        for clbit, qubit in clbit_source.items():
            if (outcome >> position[qubit]) & 1:
                bits[width - 1 - clbit] = "1"
        key = "".join(bits)
        distribution[key] = distribution.get(key, 0.0) + float(probability)
    return distribution


def ideal_counts(circuit: QuantumCircuit, shots: int, *, seed: int) -> dict[str, float]:
    """Expected noiseless counts for `shots` shots: exact probability x shots.

    A circuit the statevector cannot handle exactly (mid-circuit measurement, reset,
    classical control) falls back to a sampled Aer run seeded with `seed`, which must
    come from derive_seed like every other simulator seed.
    """
    try:
        return {key: p * shots for key, p in ideal_probabilities(circuit).items()}
    except UnsupportedIdealCircuit:
        sampled = circuit.copy()
        if sampled.num_clbits == 0:
            sampled.measure_all()
        result = AerSimulator().run(sampled, shots=shots, seed_simulator=seed).result()
        return {key.replace(" ", ""): float(n) for key, n in result.get_counts().items()}
