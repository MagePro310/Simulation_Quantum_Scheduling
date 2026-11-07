"""Unit tests for the centralized algorithm registry and heuristic algorithm discovery."""

from __future__ import annotations

import pytest

from source.algorithm.registry import (
    get_algorithm,
    list_algorithms,
    register_algorithm,
)
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic


def test_registry_lists_all_built_in_algorithms():
    """Verify registry discovers all 5 core heuristic algorithms."""
    algorithms = list_algorithms()
    assert "FFD" in algorithms
    assert "FFD_v2" in algorithms
    assert "Adaptive_FFD" in algorithms
    assert "LPT" in algorithms
    assert "QGroup" in algorithms


def test_get_algorithm_case_insensitive():
    """Verify algorithms can be instantiated by name case-insensitively."""
    ffd_upper = get_algorithm("FFD")
    ffd_lower = get_algorithm("ffd")
    assert type(ffd_upper).__name__ == "FFD"
    assert type(ffd_lower).__name__ == "FFD"

    lpt = get_algorithm("lpt")
    assert type(lpt).__name__ == "LPT"

    qgroup = get_algorithm("QGroup")
    assert type(qgroup).__name__ == "QGroup"


def test_get_algorithm_unknown_raises():
    """Verify attempting to get an unregistered algorithm raises KeyError."""
    with pytest.raises(KeyError, match="Unknown scheduling algorithm"):
        get_algorithm("NonExistentAlgorithm")


def test_custom_algorithm_registration():
    """Verify external developer can register a custom algorithm easily."""

    @register_algorithm("DummyGreedy")
    class DummyGreedy:
        def execute(self, scheduler_job, machines):
            machine_name = list(machines.keys())[0]
            for idx, job in enumerate(scheduler_job.values()):
                job.assigned_machine = machine_name
                job.dispatch_order = idx
            return scheduler_job

    assert "DummyGreedy" in list_algorithms()
    instance = get_algorithm("DummyGreedy")
    assert isinstance(instance, DummyGreedy)

    # Test execution
    machines = {
        "m1": MachineCharacteristic(name="m1", quantum_machine=None, capacity=5)
    }
    jobs = {
        "j1": SchedulerJobInfo(job_information=JobInfo(job_name="j1", num_qubits=2)),
        "j2": SchedulerJobInfo(job_information=JobInfo(job_name="j2", num_qubits=3)),
    }
    result = instance.execute(jobs, machines)
    assert result["j1"].assigned_machine == "m1"
    assert result["j1"].dispatch_order == 0
    assert result["j2"].assigned_machine == "m1"
    assert result["j2"].dispatch_order == 1
