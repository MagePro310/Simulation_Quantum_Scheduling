"""Domain models for quantum hardware machines and characteristics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from source.simulator.backends import default_rep_delay


@dataclass
class MachineCharacteristic:
    """Represents a quantum machine, its backend instance, and qubit capacity.

    rep_delay is the wait between shots, in seconds. Left as None, it is read from
    the backend (default_rep_delay), so every way of building a machine charges it.
    """

    name: str
    quantum_machine: Any
    capacity: int
    rep_delay: float | None = None

    def __post_init__(self) -> None:
        if self.rep_delay is None:
            self.rep_delay = default_rep_delay(self.quantum_machine)
        if self.rep_delay < 0:
            raise ValueError(f"rep_delay must be non-negative seconds, got {self.rep_delay}.")
