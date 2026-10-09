"""Scheduling algorithm protocol (PEP 8 compliant, no 'I' prefix).

This module defines the single architectural contract for all quantum scheduling algorithms.
"""

from typing import Protocol, runtime_checkable
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


@runtime_checkable
class ScheduleAlgorithmProtocol(Protocol):
    """Giao diện chuẩn hóa cho mọi thuật toán lập lịch lượng tử.

    Mọi thuật toán (FFD, FFD_v2, LPT, QGroup...) đều chuẩn hóa:
    - enable_optional_cutting (bool): Có bật cắt mạch tùy chọn (Stage 2) hay không.
    - optional_cutting_policy (str): Chính sách cắt tùy chọn (mặc định 'half').
    - execute(): Phương thức điều phối và gán máy.
    """

    enable_optional_cutting: bool
    optional_cutting_policy: str

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Xây dựng lịch trình và trả về scheduler_job đã được gán máy và thứ tự."""
        ...
