"""First Fit Decreasing Version 2 (FFD_v2): Circuit Cutting & Bin Packing Scheduler."""

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class FFD_v2(FFD):
    """First Fit Decreasing Version 2: Tự động sử dụng circuit cutting helper để tinh chỉnh đầu vào rồi xếp bin.

    Không yêu cầu khai báo policy khi khởi tạo. Thuật toán tự động tính toán
    và gọi công cụ cắt từ SchedulingCutterHelper với target qubit phù hợp.
    """

    def __init__(self):
        super().__init__()

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Thực thi FFD_v2: cắt mạch tối ưu hóa bằng cutting helper, sắp xếp và xếp bin."""
        if not scheduler_job:
            return scheduler_job

        max_capacity = SchedulingCutterHelper.get_max_capacity(machines)

        print("\n" + "=" * 65)
        print("  [FFD_v2] Gọi Thư Viện Cutting Helper Để Tinh Chỉnh Đầu Vào")
        print("=" * 65)
        # Cắt toàn bộ các mạch gốc đủ điều kiện với target là max_capacity (mặc định chia đôi cân bằng)
        jobs_to_schedule = SchedulingCutterHelper.cut_jobs(
            jobs=scheduler_job,
            target_qubits=max_capacity,
            min_qubits=2,
        )

        print("\n" + "=" * 65)
        print("  [FFD_v2] Xếp Bin & Gán Máy Bằng First Fit Decreasing")
        print("=" * 65)
        # 1. Phân nhóm các mạch con vào các bin theo thứ tự qubit giảm dần
        packed_bins = self.pack(jobs_to_schedule, machines)

        # 2. Sắp xếp thứ tự thực thi của các bin theo thời gian
        bins_in_execution_order = self._order_bins_by_start_time(
            packed_bins, jobs_to_schedule, machines
        )

        # 3. Gán máy và thứ tự dispatch
        self._assign_jobs(bins_in_execution_order, machines)

        return jobs_to_schedule
