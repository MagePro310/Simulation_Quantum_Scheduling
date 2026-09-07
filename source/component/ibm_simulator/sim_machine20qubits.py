"""20 Qubit Backends (5 backends)"""
from qiskit_ibm_runtime.fake_provider import FakeAlmadenV2
from qiskit_ibm_runtime.fake_provider import FakeBoeblingenV2
from qiskit_ibm_runtime.fake_provider import FakeJohannesburgV2
from qiskit_ibm_runtime.fake_provider import FakePoughkeepsieV2
from qiskit_ibm_runtime.fake_provider import FakeSingaporeV2

__all__ = [
    'FakeAlmadenV2',
    'FakeBoeblingenV2',
    'FakeJohannesburgV2',
    'FakePoughkeepsieV2',
    'FakeSingaporeV2',
]
