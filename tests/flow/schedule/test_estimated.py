"""Unit tests for flow/schedule/estimated.py::estimated_schedule.

This is currently a placeholder implementation - it returns circuit.depth()
and ignores `shots` entirely. These tests pin down that documented behavior.
"""
from qiskit import QuantumCircuit

from flow.schedule.estimated import estimated_schedule


def test_estimated_schedule_returns_circuit_depth_ignoring_shots():
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)

    result_100_shots = estimated_schedule(circuit, shots=100)
    result_100000_shots = estimated_schedule(circuit, shots=100000)

    assert result_100_shots == circuit.depth()
    assert result_100000_shots == circuit.depth()
    assert result_100_shots == result_100000_shots


def test_estimated_schedule_returns_zero_for_empty_circuit():
    circuit = QuantumCircuit(3)
    assert estimated_schedule(circuit, shots=1024) == 0
