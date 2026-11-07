from dataclasses import dataclass
from typing import Any


@dataclass
class MachineCharacteristic:
    """
    Dataclass to represent the characteristics of a quantum machine.
    """
    name: str
    quantum_machine: Any
    capacity: int