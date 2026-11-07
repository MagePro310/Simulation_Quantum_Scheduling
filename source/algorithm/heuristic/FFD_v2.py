"""First Fit Decreasing Version 2 (FFD_v2): Circuit Cutting & Bin Packing Scheduler."""

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class FFD_v2(FFD):
    """First Fit Decreasing Version 2: Applies circuit cutting helper to optimize input before bin packing.

    Does not require an explicit policy at initialization. The algorithm dynamically calculates
    and invokes the cutting helper with the appropriate target qubit capacity.
    """

    def __init__(self):
        super().__init__()

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Execute FFD_v2: optimize circuits via cutting helper, sort, and bin-pack."""
        if not scheduler_job:
            return scheduler_job

        max_capacity = SchedulingCutterHelper.get_max_capacity(machines)

        print("\n" + "=" * 65)
        print("  [FFD_v2] Invoking Circuit Cutting Helper To Refine Input")
        print("=" * 65)
        # Cut all eligible root circuits targeting max_capacity (default balanced partition)
        jobs_to_schedule = SchedulingCutterHelper.cut_jobs(
            jobs=scheduler_job,
            target_qubits=max_capacity,
            min_qubits=2,
        )

        print("\n" + "=" * 65)
        print("  [FFD_v2] Bin Packing & Machine Assignment via First Fit Decreasing")
        print("=" * 65)
        # 1. Group subcircuits into bins in decreasing qubit order
        packed_bins = self.pack(jobs_to_schedule, machines)

        # 2. Order bins execution by start time
        bins_in_execution_order = self._order_bins_by_start_time(
            packed_bins, jobs_to_schedule, machines
        )

        # 3. Assign machines and dispatch orders
        self._assign_jobs(bins_in_execution_order, machines)

        return jobs_to_schedule
