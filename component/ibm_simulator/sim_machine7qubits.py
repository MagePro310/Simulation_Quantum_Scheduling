"""7 Qubit Backends (6 backends)"""
from qiskit_ibm_runtime.fake_provider import FakeCasablancaV2
from qiskit_ibm_runtime.fake_provider import FakeJakartaV2
from qiskit_ibm_runtime.fake_provider import FakeLagosV2
from qiskit_ibm_runtime.fake_provider import FakeNairobiV2
from qiskit_ibm_runtime.fake_provider import FakeOslo
from qiskit_ibm_runtime.fake_provider import FakePerth

__all__ = [
    'FakeCasablancaV2',
    'FakeJakartaV2',
    'FakeLagosV2',
    'FakeNairobiV2',
    'FakeOslo',
    'FakePerth',
]
