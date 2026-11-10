"""Choose which qubits go into which subcircuit so a gate cut is as cheap as possible.

The caller (PreSchedule or an algorithm) fixes the subcircuit sizes, e.g. [5, 2]. Which
qubits fill each subcircuit is free, and it decides which two-qubit gates are cut:
for a 6-qubit Deutsch-Jozsa circuit split [5, 1], putting the ancilla alone cuts five
CNOTs (sampling overhead 9^5) while putting any other qubit alone cuts one (overhead 9).

The cost of a cut is its sampling overhead, the product of the cut gates' QPD overheads
(gamma^2: 9 per CNOT, less for small-angle phase gates). Taking logs makes it a sum
over the edges of the weighted qubit interaction graph, so the problem is a graph
partition with fixed part sizes. Circuits small enough to reconstruct (the
reconstruction is O(4^n)) are solved exactly by enumeration; larger ones by a
deterministic local search from the contiguous assignment.

Ties go to the lexicographically smallest label vector, which is the contiguous
assignment whenever that is optimal, so circuits like GHZ cut exactly as before.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from qiskit import QuantumCircuit
from qiskit_addon_cutting.qpd import QPDBasis

# Above this many assignments, local search replaces enumeration
MAX_ENUMERATED_ASSIGNMENTS = 200_000
_TOLERANCE = 1e-9
_NON_GATES = {"barrier", "measure", "delay", "reset"}


class CutBudgetExceeded(ValueError):
    """The cheapest cut of a circuit needs more subexperiments than the budget allows."""


@dataclass(frozen=True)
class CutPlan:
    """Qubit-to-subcircuit assignment and what cutting with it costs.

    labels[q] is the index of the subcircuit holding qubit q (0 for the first size).
    overhead is the QPD sampling overhead (0.0 when no gate is cut, by convention).
    num_subexperiments is the number of subexperiment circuits each subcircuit runs.
    """

    labels: tuple[int, ...]
    overhead: float
    num_subexperiments: int
    num_cuts: int


_GATE_COST_CACHE: dict[tuple, tuple[float, int]] = {}


def _gate_cost(operation) -> tuple[float, int]:
    """(QPD sampling overhead, number of QPD terms) for cutting one two-qubit gate."""
    key = (operation.name, tuple(float(p) for p in operation.params))
    if key not in _GATE_COST_CACHE:
        basis = QPDBasis.from_instruction(operation)
        _GATE_COST_CACHE[key] = (float(basis.overhead), len(basis.maps))
    return _GATE_COST_CACHE[key]


def _two_qubit_gates(circuit: QuantumCircuit) -> list[tuple[int, int, float, int]]:
    """(qubit a, qubit b, overhead, QPD terms) for every two-qubit gate."""
    gates = []
    for instruction in circuit.data:
        operation = instruction.operation
        if operation.name in _NON_GATES or len(instruction.qubits) != 2:
            continue
        a, b = (circuit.find_bit(q).index for q in instruction.qubits)
        overhead, terms = _gate_cost(operation)
        gates.append((a, b, overhead, terms))
    return gates


def _weights(num_qubits: int, gates) -> np.ndarray:
    weights = np.zeros((num_qubits, num_qubits))
    for a, b, overhead, _ in gates:
        weights[a, b] += math.log(overhead)
        weights[b, a] += math.log(overhead)
    return weights


def _num_assignments(sizes: list[int]) -> int:
    count = math.factorial(sum(sizes))
    for size in sizes:
        count //= math.factorial(size)
    return count


def _contiguous(sizes: list[int]) -> list[int]:
    return [part for part, size in enumerate(sizes) for _ in range(size)]


def _cut_weight(labels, weights: np.ndarray) -> float:
    n = len(labels)
    return float(sum(weights[i, j] for i in range(n) for j in range(i + 1, n) if labels[i] != labels[j]))


def _enumerate(weights: np.ndarray, sizes: list[int]) -> list[int]:
    """Exact minimum by depth-first search in lexicographic order of label vectors."""
    n = len(weights)
    labels = [0] * n
    remaining = list(sizes)
    best_cost = math.inf
    best_labels: list[int] = _contiguous(sizes)

    def visit(qubit: int, cost: float) -> None:
        nonlocal best_cost, best_labels
        if cost >= best_cost - _TOLERANCE:
            return  # weights are non-negative, so the cost can only grow
        if qubit == n:
            best_cost, best_labels = cost, list(labels)
            return
        for part in range(len(sizes)):
            if remaining[part] == 0:
                continue
            added = sum(weights[p, qubit] for p in range(qubit) if labels[p] != part)
            labels[qubit] = part
            remaining[part] -= 1
            visit(qubit + 1, cost + added)
            remaining[part] += 1

    visit(0, 0.0)
    return best_labels


def _local_search(weights: np.ndarray, sizes: list[int]) -> list[int]:
    """Best-improving pairwise swaps from the contiguous assignment, until none improves."""
    labels = _contiguous(sizes)
    n = len(labels)
    while True:
        best_delta, best_pair = -_TOLERANCE, None
        for i in range(n):
            for j in range(i + 1, n):
                if labels[i] == labels[j]:
                    continue
                # Moving i to labels[j] and j to labels[i]
                delta = 0.0
                for k in range(n):
                    if k in (i, j):
                        continue
                    delta += weights[i, k] * ((labels[k] != labels[j]) - (labels[k] != labels[i]))
                    delta += weights[j, k] * ((labels[k] != labels[i]) - (labels[k] != labels[j]))
                if delta < best_delta:
                    best_delta, best_pair = delta, (i, j)
        if best_pair is None:
            return labels
        i, j = best_pair
        labels[i], labels[j] = labels[j], labels[i]


def plan_cut(circuit: QuantumCircuit, sizes: list[int]) -> CutPlan:
    """Cheapest assignment of the circuit's qubits to subcircuits of the given sizes."""
    sizes = list(sizes)
    if sum(sizes) != circuit.num_qubits or any(size <= 0 for size in sizes):
        raise ValueError(f"Partition sizes {sizes} do not split {circuit.num_qubits} qubits.")

    gates = _two_qubit_gates(circuit)
    weights = _weights(circuit.num_qubits, gates)
    if _num_assignments(sizes) <= MAX_ENUMERATED_ASSIGNMENTS:
        labels = _enumerate(weights, sizes)
    else:
        labels = _local_search(weights, sizes)

    cut = [(overhead, terms) for a, b, overhead, terms in gates if labels[a] != labels[b]]
    return CutPlan(
        labels=tuple(labels),
        overhead=float(math.prod(o for o, _ in cut)) if cut else 0.0,
        num_subexperiments=int(math.prod(t for _, t in cut)) if cut else 1,
        num_cuts=len(cut),
    )
