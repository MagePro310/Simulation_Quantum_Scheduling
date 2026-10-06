"""Tests for Hellinger fidelity calculation and execution integration."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import hellinger_fidelity

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.component.ibm_simulator.sim_machine5qubits import FakeBelemV2
from source.component.help_function.fidelity import (
    compute_hellinger_fidelity,
    compute_total_variation_distance,
)
from source.flow.execution.orchestrator import ConcreteExecutionPhase


def test_hellinger_fidelity_reference_example():
    """Verify compute_hellinger_fidelity matches hellinger_fidelity.py."""
    counts_ideal = {'00': 500, '11': 500}
    counts_noisy = {'00': 480, '11': 470, '01': 30, '10': 20}

    expected_fid = float(hellinger_fidelity(counts_ideal, counts_noisy))
    actual_fid = compute_hellinger_fidelity(counts_ideal, counts_noisy)

    assert pytest.approx(actual_fid, rel=1e-6) == expected_fid
    assert pytest.approx(actual_fid, rel=1e-4) == 0.94997


def test_hellinger_fidelity_identical_and_orthogonal():
    """Verify identical distributions yield 1.0 and orthogonal yield 0.0."""
    c1 = {'00': 1024}
    c2 = {'00': 1024}
    c3 = {'11': 1024}

    assert compute_hellinger_fidelity(c1, c2) == 1.0
    assert compute_hellinger_fidelity(c1, c3) == 0.0

    assert compute_total_variation_distance(c1, c2) == 0.0
    assert compute_total_variation_distance(c1, c3) == 1.0


def test_hellinger_fidelity_edge_cases():
    """Verify edge cases like empty dicts and None."""
    assert compute_hellinger_fidelity({}, {}) == 1.0
    assert compute_hellinger_fidelity({'0': 100}, {}) == 0.0
    assert compute_hellinger_fidelity({}, {'0': 100}) == 0.0
    assert compute_hellinger_fidelity(None, {'0': 100}) == 0.0

    assert compute_total_variation_distance({}, {}) == 0.0
    assert compute_total_variation_distance({'0': 100}, {}) == 1.0
    assert compute_total_variation_distance(None, {'0': 100}) == 1.0


def test_execution_phase_calculates_hellinger_fidelity():
    """Verify ConcreteExecutionPhase computes Hellinger fidelity on executed jobs."""
    # Create simple 2-qubit Bell circuit
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    job = JobInfo(
        job_name="bell_job",
        circuit=qc,
        num_qubits=2,
        shots=512,
        arrival_time=0.0,
    )

    machine = MachineCharacteristic(name="belem", quantum_machine=FakeBelemV2(), capacity=5)
    sched_job = SchedulerJobInfo(
        job_information=job,
        assigned_machine="belem",
        dispatch_order=1,
    )

    capture_result = ResultOfSchedule()
    exec_phase = ConcreteExecutionPhase()
    results = exec_phase.execute(
        machines={"belem": machine},
        scheduler_job={"bell_job": sched_job},
        capture_result_schedule=capture_result,
        seed=42,
    )

    assert "bell_job" in results
    res = results["bell_job"]
    assert res.status == "SUCCEEDED"
    assert res.fidelity is not None
    assert 0.0 <= res.fidelity <= 1.0
    assert res.hellinger_fidelity == res.fidelity
    assert res.bhattacharyya_fidelity == res.fidelity
    assert res.tvd is not None
    assert 0.0 <= res.tvd <= 1.0

    # Ensure execution summary has average fidelity
    assert capture_result.execution_summary is not None
    assert capture_result.execution_summary.average_fidelity == res.fidelity
