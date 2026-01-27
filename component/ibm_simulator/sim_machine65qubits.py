"""65 Qubit Backends (2 backends)"""
from qiskit_ibm_runtime.fake_provider import FakeBrooklynV2
from qiskit_ibm_runtime.fake_provider import FakeManhattanV2

__all__ = [
    'FakeBrooklynV2',
    'FakeManhattanV2',
]
