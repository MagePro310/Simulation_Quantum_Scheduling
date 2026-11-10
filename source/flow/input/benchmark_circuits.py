"""Load benchmark circuits in a gate set every later phase can handle.

MQT Bench's ALG level wraps whole algorithms in composite gates (a single `qft`,
`Oracle` or `Q` gate). Those break the pipeline: circuit cutting only decomposes
standard two-qubit gates, Aer cannot simulate the ideal baseline, and the depth
and gate counts that schedulers estimate durations from are meaningless (an ALG
QFT has depth 2; transpiled, it has depth 38).

The INDEP level is decomposed into standard gates, but still independent of any
device. A few benchmarks keep composite or multi-qubit gates even there, so any
gate that is not a standard gate on at most two qubits is decomposed further.
"""

from __future__ import annotations

from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit import QuantumCircuit
from qiskit.circuit.library.standard_gates import get_standard_gate_name_mapping

BENCHMARK_LEVEL = BenchmarkLevel.INDEP
_DIRECTIVES = {"measure", "barrier", "reset", "delay"}
_STANDARD_GATES = set(get_standard_gate_name_mapping())
_MAX_DECOMPOSE_ROUNDS = 10


def _gates_to_expand(circuit: QuantumCircuit) -> set[str]:
    """Names of operations that are not directives or standard gates on at most two qubits."""
    return {
        instruction.operation.name
        for instruction in circuit.data
        if instruction.operation.name not in _DIRECTIVES
        and (
            instruction.operation.name not in _STANDARD_GATES
            or instruction.operation.num_qubits > 2
        )
    }


def expand_to_two_qubit_gates(circuit: QuantumCircuit) -> QuantumCircuit:
    """Decompose composite and multi-qubit gates until only standard 1- and 2-qubit gates remain.

    Raises:
        ValueError: If some gate cannot be decomposed that far.
    """
    expanded = circuit
    for _ in range(_MAX_DECOMPOSE_ROUNDS):
        pending = _gates_to_expand(expanded)
        if not pending:
            return expanded
        expanded = expanded.decompose(gates_to_decompose=sorted(pending))
    remaining = _gates_to_expand(expanded)
    if remaining:
        raise ValueError(
            f"Circuit {circuit.name!r} still has gates {sorted(remaining)} after "
            f"{_MAX_DECOMPOSE_ROUNDS} decomposition rounds."
        )
    return expanded


def load_benchmark_circuit(benchmark: str, num_qubits: int) -> QuantumCircuit:
    """Return an MQT Bench circuit at the INDEP level, with only standard 1- and 2-qubit gates.

    A benchmark without measurements (e.g. qaoa) gets measure_all(): every job must
    produce an output distribution for fidelity and multi-programmed count splitting.
    """
    circuit = expand_to_two_qubit_gates(
        get_benchmark(benchmark, level=BENCHMARK_LEVEL, circuit_size=num_qubits)
    )
    if circuit.num_clbits == 0:
        circuit.measure_all()
    return circuit
