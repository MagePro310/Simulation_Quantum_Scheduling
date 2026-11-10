"""Conditional crosstalk between simultaneous two-qubit gates, after Murali et al. (ASPLOS 2020).

The backend noise models from `AerSimulator.from_backend` have gate, readout and
relaxation errors but no crosstalk, which is the main cost of multi-programming.
Following the conditional-error model of simultaneous randomized benchmarking:

- two two-qubit gates are *neighbours* if their qubit pairs are disjoint and some
  qubit of one is coupled to some qubit of the other on the device;
- a gate whose time interval on the ALAP schedule overlaps a neighbour's has its
  error raised from eps to k * eps, where eps is the gate's calibrated error from
  the backend target and k (`crosstalk_factor`) is an assumption, since the fake
  backends carry no crosstalk data. The extra (k - 1) * eps is a two-qubit
  depolarizing channel placed right after the gate, applied once however many
  neighbours overlap (Murali et al. measure conditional errors pairwise).

Gates of the same job and of different jobs are treated alike: crosstalk is physical.
Always-on ZZ coupling of idle qubits is not modelled.
"""

from __future__ import annotations

from typing import Any

from qiskit import QuantumCircuit
from qiskit.quantum_info import Kraus
from qiskit_aer import AerSimulator
from qiskit_aer.noise import depolarizing_error

_NO_DURATION = {"barrier"}


def noisy_simulator(backend: Any) -> AerSimulator:
    """The backend's noisy simulator, as both batch paths must build it.

    The method is fixed to statevector (noise by trajectories). Left on automatic,
    Aer picks density_matrix for circuits holding Kraus channels, and Aer's SamplerV2
    then returns no memory for some classical registers of the joint QPD circuits.
    """
    return AerSimulator.from_backend(backend, method="statevector")


def _coupled_pairs(backend: Any) -> set[frozenset[int]]:
    coupling = getattr(backend, "coupling_map", None)
    if coupling is None:
        return set()
    return {frozenset(edge) for edge in coupling.get_edges() if edge[0] != edge[1]}


def _duration_dt(circuit: QuantumCircuit, instruction, backend: Any) -> int:
    """Duration of one instruction in units of dt (0 if the target gives none)."""
    operation = instruction.operation
    dt = getattr(backend, "dt", None) or 1.0
    if operation.name == "delay":
        if operation.unit == "dt":
            return int(operation.duration)
        seconds = float(operation.duration) * {"s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12}[operation.unit]
        return int(round(seconds / dt))
    if operation.name in _NO_DURATION:
        return 0
    qargs = tuple(circuit.find_bit(q).index for q in instruction.qubits)
    try:
        props = backend.target[operation.name][qargs]
    except (KeyError, TypeError):
        return 0
    duration = getattr(props, "duration", None)
    return int(round(duration / dt)) if duration else 0


def two_qubit_gate_timeline(circuit: QuantumCircuit, backend: Any) -> list[tuple[int, int, int, tuple[int, int]]]:
    """(instruction index, start, end, qubits) of every two-qubit gate, times in dt.

    The circuit must be scheduled with its idle time padded by delays (as
    `build_pass_manager` does), so accumulating durations per qubit reproduces the
    schedule. Barriers synchronise their qubits.
    """
    clock = [0] * circuit.num_qubits
    gates = []
    for index, instruction in enumerate(circuit.data):
        qubits = [circuit.find_bit(q).index for q in instruction.qubits]
        if not qubits:
            continue
        start = max(clock[q] for q in qubits)
        end = start + _duration_dt(circuit, instruction, backend)
        for q in qubits:
            clock[q] = end
        operation = instruction.operation
        if len(qubits) == 2 and operation.name not in ("barrier", "delay", "measure") and end > start:
            gates.append((index, start, end, (qubits[0], qubits[1])))
    return gates


def _neighbours(pair_a: tuple[int, int], pair_b: tuple[int, int], coupled: set[frozenset[int]]) -> bool:
    if set(pair_a) & set(pair_b):
        return False
    return any(frozenset((a, b)) in coupled for a in pair_a for b in pair_b)


def crosstalk_gate_indices(circuit: QuantumCircuit, backend: Any) -> tuple[set[int], int]:
    """Indices of two-qubit gates that overlap a neighbouring two-qubit gate, and the
    number of two-qubit gates in the circuit."""
    coupled = _coupled_pairs(backend)
    gates = two_qubit_gate_timeline(circuit, backend)
    affected: set[int] = set()
    for i, (index_a, start_a, end_a, pair_a) in enumerate(gates):
        for index_b, start_b, end_b, pair_b in gates[i + 1:]:
            if start_a < end_b and start_b < end_a and _neighbours(pair_a, pair_b, coupled):
                affected.update((index_a, index_b))
    return affected, len(gates)


def _gate_error(circuit: QuantumCircuit, instruction, backend: Any) -> float:
    qargs = tuple(circuit.find_bit(q).index for q in instruction.qubits)
    try:
        error = backend.target[instruction.operation.name][qargs].error
    except (KeyError, TypeError):
        return 0.0
    return float(error or 0.0)


def extra_depolarizing_param(gate_error: float, factor: float) -> float:
    """Two-qubit depolarizing parameter whose average gate infidelity is (factor-1)*error.

    For a d-dimensional depolarizing channel with parameter lambda, the average gate
    infidelity is lambda * (d - 1) / d, so lambda = infidelity * 4/3 for two qubits.
    """
    infidelity = max(factor - 1.0, 0.0) * gate_error
    return min(infidelity * 4.0 / 3.0, 1.0)


def apply_crosstalk(circuit: QuantumCircuit, backend: Any, factor: float) -> tuple[QuantumCircuit, int, int]:
    """Return (circuit with crosstalk channels, exposed gate count, two-qubit gate count).

    Exposed gates are two-qubit gates overlapping a neighbour, counted whatever the
    factor, so exposure can be reported even with crosstalk off. With factor 1 the
    input circuit itself is returned. The channels have no duration, so the circuit's
    timing is unchanged.
    """
    exposed, num_two_qubit = crosstalk_gate_indices(circuit, backend)
    if factor <= 1.0 or not exposed:
        return circuit, len(exposed), num_two_qubit

    noisy = circuit.copy_empty_like()
    for index, instruction in enumerate(circuit.data):
        noisy.append(instruction)
        if index in exposed:
            param = extra_depolarizing_param(_gate_error(circuit, instruction, backend), factor)
            if param > 0:
                # As a Kraus instruction: Aer 0.17's statevector method rejects some
                # QuantumError instructions in these circuits ("Kraus is empty")
                noisy.append(Kraus(depolarizing_error(param, 2)), instruction.qubits)
    return noisy, len(exposed), num_two_qubit
