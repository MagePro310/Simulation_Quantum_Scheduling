"""
Fake Quantum Backends Organized by Qubit Count
===============================================
This module provides IBM fake quantum backends organized by their qubit capacity.

Usage Examples:
    # Import specific qubit group
    from component.a_backend import fake_backend
    
    # Access 5-qubit backends
    backend = fake_backend.machine5qubits.FakeBelemV2()
    print(backend.num_qubits)  # Output: 5
    
    # Access 27-qubit backends  
    backend = fake_backend.machine27qubits.FakeHanoiV2()
    
    # Access 127-qubit backends
    backend = fake_backend.machine127qubits.FakeKyoto()

Available modules:
    - machine1qubit: 1 backend (1 qubit)
    - machine5qubits: 15 backends (5 qubits)
    - machine7qubits: 6 backends (7 qubits)
    - machine15qubits: 1 backend (15 qubits)
    - machine16qubits: 1 backend (16 qubits)
    - machine20qubits: 5 backends (20 qubits)
    - machine27qubits: 12 backends (27 qubits)
    - machine28qubits: 1 backend (28 qubits)
    - machine33qubits: 1 backend (33 qubits)
    - machine53qubits: 1 backend (53 qubits)
    - machine65qubits: 2 backends (65 qubits)
    - machine127qubits: 9 backends (127 qubits)
    - machine133qubits: 1 backend (133 qubits)
    - machine156qubits: 1 backend (156 qubits)
    - special_backends: Special backends
"""

# Import all sub-modules
from . import sim_machine1qubit
from . import sim_machine5qubits
from . import sim_machine7qubits
from . import sim_machine15qubits
from . import sim_machine16qubits
from . import sim_machine20qubits
from . import sim_machine27qubits
from . import sim_machine28qubits
from . import sim_machine33qubits
from . import sim_machine53qubits
from . import sim_machine65qubits
from . import sim_machine127qubits
from . import sim_machine133qubits
from . import sim_machine156qubits
from . import sim_special_backends

# For backward compatibility - import all backends directly
from .sim_machine1qubit import *
from .sim_machine5qubits import *
from .sim_machine7qubits import *
from .sim_machine15qubits import *
from .sim_machine16qubits import *
from .sim_machine20qubits import *
from .sim_machine27qubits import *
from .sim_machine28qubits import *
from .sim_machine33qubits import *
from .sim_machine53qubits import *
from .sim_machine65qubits import *
from .sim_machine127qubits import *
from .sim_machine133qubits import *
from .sim_machine156qubits import *
from .sim_special_backends import *

__all__ = [
    'sim_machine1qubit',
    'sim_machine5qubits',
    'sim_machine7qubits',
    'sim_machine15qubits',
    'sim_machine16qubits',
    'sim_machine20qubits',
    'sim_machine27qubits',
    'sim_machine28qubits',
    'sim_machine33qubits',
    'sim_machine53qubits',
    'sim_machine65qubits',
    'sim_machine127qubits',
    'sim_machine133qubits',
    'sim_machine156qubits',
    'sim_special_backends',
]