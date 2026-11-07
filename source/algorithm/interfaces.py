"""Scheduling algorithm protocol (PEP 8 compliant, no 'I' prefix).

This module defines the single architectural contract for all quantum scheduling algorithms.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from source.models.job import SchedulerJobInfo
from source.models.machine import MachineCharacteristic


@runtime_checkable
class ScheduleAlgorithmProtocol(Protocol):
    """Standardized protocol for quantum scheduling algorithms.

    All algorithms (FFD, FFD_v2, Adaptive_FFD, LPT, QGroup, etc.) implement
    the execute() method.
    """

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Construct schedule and return scheduler_job with machine assignments and dispatch orders."""
        ...


__all__ = ["ScheduleAlgorithmProtocol"]
