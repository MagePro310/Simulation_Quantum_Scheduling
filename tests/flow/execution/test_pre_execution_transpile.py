"""Unit tests for flow/execution/pre_execution_transpile.py::PreExecution.compose.

transpile_jobs() is intentionally out of scope: it requires a real/fake
qiskit backend and calls qiskit.compiler.transpile, which falls outside the
pure-logic scope of this suite.
"""
from types import SimpleNamespace

import pytest
from qiskit import QuantumCircuit

from flow.execution.pre_execution_transpile import PreExecution


def test_compose_raises_value_error_for_empty_list():
    with pytest.raises(ValueError, match="At least one circuit is required"):
        PreExecution().compose([])


def test_compose_merges_qubit_and_clbit_counts_across_jobs():
    qc1 = QuantumCircuit(2, 2)
    qc1.h(0)
    qc1.measure(0, 0)
    qc2 = QuantumCircuit(3, 1)
    qc2.x(0)
    qc2.measure(0, 0)

    merged = PreExecution().compose([SimpleNamespace(circuit=qc1), SimpleNamespace(circuit=qc2)])

    assert merged.num_qubits == 5
    assert merged.num_clbits == 3


def test_compose_omits_classical_register_when_no_job_has_clbits():
    qc1 = QuantumCircuit(1, 0)
    qc1.h(0)
    qc2 = QuantumCircuit(1, 0)
    qc2.x(0)

    merged = PreExecution().compose([SimpleNamespace(circuit=qc1), SimpleNamespace(circuit=qc2)])

    assert merged.num_qubits == 2
    assert merged.num_clbits == 0
    assert len(merged.cregs) == 0
    assert len(merged.qregs) == 1


def test_compose_places_each_job_circuit_at_correct_qubit_offset():
    qc_a = QuantumCircuit(2, 0)
    qc_a.x(0)
    qc_a.x(1)
    qc_b = QuantumCircuit(1, 0)
    qc_b.h(0)

    merged = PreExecution().compose([SimpleNamespace(circuit=qc_a), SimpleNamespace(circuit=qc_b)])

    gate_by_qubit = {
        merged.find_bit(instr.qubits[0]).index: instr.operation.name for instr in merged.data
    }
    # qc_a occupies qubits [0, 1]; qc_b is offset to start at qubit 2.
    assert gate_by_qubit == {0: "x", 1: "x", 2: "h"}


def test_compose_accepts_simplenamespace_with_circuit_attribute():
    qc = QuantumCircuit(1, 0)
    qc.h(0)

    merged = PreExecution().compose([SimpleNamespace(circuit=qc)])

    assert merged.num_qubits == 1


def test_compose_single_job_returns_equivalent_single_register_circuit():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.measure(0, 0)

    merged = PreExecution().compose([SimpleNamespace(circuit=qc)])

    assert merged.num_qubits == 2
    assert merged.num_clbits == 2
    ops = [instr.operation.name for instr in merged.data]
    assert ops == ["h", "measure"]
