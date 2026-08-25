"""Plain, non-fixture test helpers shared across the suite.

Deliberately not a conftest.py: nothing here needs pytest's fixture
lifecycle (setup/teardown, name-based injection) -- these are just factory
functions/classes, kept as explicit imports for traceability.
"""
from types import SimpleNamespace

from component.dataclass.job_info import JobInfo, SchedulerJobInfo


class FakeCircuit:
    """Minimal circuit stand-in exposing exactly what FFD needs: num_qubits
    and a callable depth(). SimpleNamespace can't provide the latter."""

    def __init__(self, num_qubits: int, depth_value: int = 1):
        self.num_qubits = num_qubits
        self._depth_value = depth_value

    def depth(self) -> int:
        return self._depth_value


def make_machine(num_qubits: int) -> SimpleNamespace:
    return SimpleNamespace(num_qubits=num_qubits)


def make_scheduler_job(
    name: str,
    num_qubits: int,
    depth_value: int = 1,
    arrival_time: float = 0.0,
    shots: int | None = None,
) -> SchedulerJobInfo:
    """Build a SchedulerJobInfo wrapping a FakeCircuit, for FFD tests."""
    circuit = FakeCircuit(num_qubits=num_qubits, depth_value=depth_value)
    job_information = JobInfo(
        job_name=name, circuit=circuit, shots=shots, arrival_time=arrival_time
    )
    return SchedulerJobInfo(job_information=job_information)
