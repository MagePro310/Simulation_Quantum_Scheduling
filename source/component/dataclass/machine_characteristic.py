from dataclasses import dataclass
from typing import Any
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

@dataclass
class MachineCharacteristic:
    """
    Dataclass to represent the characteristics of a quantum machine.
    """
    name: str
    quantum_machine: Any
    capacity: int