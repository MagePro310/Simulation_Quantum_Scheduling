"""127 Qubit Backends (9 backends)"""
from qiskit_ibm_runtime.fake_provider import FakeBrisbane
from qiskit_ibm_runtime.fake_provider import FakeCusco
from qiskit_ibm_runtime.fake_provider import FakeKawasaki
from qiskit_ibm_runtime.fake_provider import FakeKyiv
from qiskit_ibm_runtime.fake_provider import FakeKyoto
from qiskit_ibm_runtime.fake_provider import FakeOsaka
from qiskit_ibm_runtime.fake_provider import FakeQuebec
from qiskit_ibm_runtime.fake_provider import FakeSherbrooke
from qiskit_ibm_runtime.fake_provider import FakeWashingtonV2

__all__ = [
    'FakeBrisbane',
    'FakeCusco',
    'FakeKawasaki',
    'FakeKyiv',
    'FakeKyoto',
    'FakeOsaka',
    'FakeQuebec',
    'FakeSherbrooke',
    'FakeWashingtonV2',
]
