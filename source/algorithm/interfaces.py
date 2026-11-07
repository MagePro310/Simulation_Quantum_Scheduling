"""Scheduling algorithm protocol (PEP 8 compliant, no 'I' prefix).

This module defines the single architectural contract for all quantum scheduling algorithms.
"""

from typing import Protocol, runtime_checkable
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


@runtime_checkable
class ScheduleAlgorithmProtocol(Protocol):
    """Standardized protocol for quantum scheduling algorithms.

    All algorithms (FFD, FFD_v2, LPT, QGroup, etc.) implement the execute() method.
    If an algorithm requires circuit cutting, it can directly utilize
    `from source.algorithm import SchedulingCutterHelper`.
    """

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Construct schedule and return scheduler_job with machine assignments and dispatch orders."""
        ...
