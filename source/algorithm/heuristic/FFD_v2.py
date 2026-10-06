"""First Fit Decreasing Version 2 (FFD_v2): Autonomous Cutting & Re-ordering Scheduler."""

from source.algorithm.heuristic.FFD import FFD
from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper


class FFD_v2(FFD):
    """First Fit Decreasing Version 2 with Integrated Autonomous Circuit Chopping.

    Unlike standard FFD (which takes incoming circuits as-is), FFD_v2 proactively
    decides to apply half-cut to all eligible uncut circuits (num_qubits >= 2) before scheduling.
    
    This proactive chopping creates smaller, more flexible subcircuits to:
        1. Reduce QPU idle space (slack) during bin packing.
        2. Balance workload across heterogeneous quantum machines.
        3. Dynamically re-order all subcircuits decreasingly by qubit footprint.

    Flow:
        1. Cutting Decision & Execution: Proactively half-cut all eligible uncut circuits.
        2. Re-ordering: Re-sort the entire pool of original and chopped subcircuits largest-first.
        3. Bin Packing: First Fit Decreasing packing across machine bins.
        4. Dependency & Machine Assignment: Sequence bins and set machine dispatch barriers.
    """

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Execute FFD_v2: chop circuits, re-order, and pack into machine bins."""
        if not scheduler_job:
            return scheduler_job

        max_capacity = max(
            (getattr(m, "capacity", 0) for m in machines.values()),
            default=0,
        )

        print("\n" + "=" * 65)
        print("  [FFD_v2] Stage 1: Autonomous Cutting Decision (Half-Cut Chopping)")
        print("=" * 65)
        chopped_jobs = SchedulingCutterHelper.apply_half_cut_to_jobs(
            scheduler_job=scheduler_job,
            max_capacity=max_capacity,
            min_qubits=2,
        )

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

