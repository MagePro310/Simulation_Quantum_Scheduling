"""First Fit Decreasing Version 2 (FFD_v2): Autonomous Cutting & Re-ordering Scheduler."""

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class FFD_v2(FFD):
    """First Fit Decreasing Version 2 with Integrated Proactive Circuit Chopping.

    FFD_v2 2-Stage Cutting Workflow:
        1. Initial Stage (Ban đầu): Mandatory exceed cutting using 'greedy' policy
           to ensure all circuits physically fit within maximum machine capacity.
        2. Optimization Stage (Xong / Sau đó): Proactively applies 'half' cut
           to ALL remaining uncut circuits (num_qubits >= 2) to reduce QPU slack.
        3. Scheduling Stage: Dynamically re-orders all subcircuits decreasingly
           by qubit footprint (largest first) and packs them via First Fit Decreasing.
    """

    enable_optional_cutting: bool = True
    optional_cutting_policy: str = "half"

    def __init__(
        self,
        enable_optional_cutting: bool = True,
        optional_cutting_policy: str = "half",
    ):
        super().__init__()
        self.enable_optional_cutting = enable_optional_cutting
        self.optional_cutting_policy = optional_cutting_policy

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Execute FFD_v2: ensure all circuits are half-cut, re-order, and pack into machine bins."""
        if not scheduler_job:
            return scheduler_job

        max_capacity = max(
            (getattr(m, "capacity", 0) for m in machines.values()),
            default=0,
        )

        if self.enable_optional_cutting:
            print("\n" + "=" * 65)
            print("  [FFD_v2] Stage 1: Autonomous Cutting Decision (Half-Cut Chopping)")
            print("=" * 65)
            chopped_jobs = SchedulingCutterHelper.apply_half_cut_to_jobs(
                scheduler_job=scheduler_job,
                max_capacity=max_capacity,
                min_qubits=2,
            )
        else:
            chopped_jobs = scheduler_job

        print("\n" + "=" * 65)
        print("  [FFD_v2] Stage 2: Re-ordering & First Fit Decreasing Bin Packing")
        print("=" * 65)
        # 1. Group jobs into machine bins using First Fit Decreasing (re-orders largest first).
        packed_bins = self.pack(chopped_jobs, machines)

        # 2. Use estimated durations to order the occupied bins by start time.
        bins_in_execution_order = self._order_bins_by_start_time(
            packed_bins, chopped_jobs, machines
        )

        # 3. Write each job's machine, dispatch order, and dependencies.
        self._assign_jobs(bins_in_execution_order, machines)

        return chopped_jobs

