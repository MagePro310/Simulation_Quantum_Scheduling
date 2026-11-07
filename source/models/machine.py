"""Domain models for quantum hardware machines and characteristics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MachineCharacteristic:
    """Represents a quantum machine, its backend instance, and qubit capacity."""

    name: str
    quantum_machine: Any
    capacity: int
