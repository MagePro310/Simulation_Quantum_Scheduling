"""Scheduling phase orchestrating pre-schedule mandatory cutting and algorithm execution (Phase 2)."""

from __future__ import annotations

import time
from typing import Any

from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper
from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.models.job import JobInfo, SchedulerJobInfo


class SchedulePhase:
    """Orchestrates pre-schedule circuit preparation (mandatory exceed) and algorithm execution."""

    def __init__(
        self,
        algorithm: Any = None,
        exceed_cutting_policy: str = "greedy",
        **kwargs,
    ):
        self.algorithm = algorithm
        self.exceed_cutting_policy = exceed_cutting_policy.lower()
        self.pre_phase = PreSchedulePhase(exceed_cutting_policy=self.exceed_cutting_policy)

    def set_exceed_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy for oversized circuits: 'greedy' or 'half'."""
        self.exceed_cutting_policy = policy.lower()
        self.pre_phase.set_exceed_cutting_policy(self.exceed_cutting_policy)

    def execute(
        self,
        origin_job_info: dict[str, JobInfo],
        machines: dict[str, Any],
        capture_result_schedule: Any,
    ) -> dict[str, SchedulerJobInfo]:
        """Execute pre-scheduling mandatory cut and the chosen algorithm.

        Args:
            origin_job_info: Original input circuits.
            machines: Target machine specifications.
            capture_result_schedule: Dataclass to record scheduling metadata.

        Returns:
            Dictionary of SchedulerJobInfo with assignments and dispatch orders.
        """
        # Step 1: Pre-phase prepares circuits (mandatory exceed cut only)
        scheduler_job = self.pre_phase.execute(origin_job_info, machines)

        # Step 2: Main schedule algorithm executes directly
        algo_name = getattr(self.algorithm, "__class__", type("Default", (), {})).__name__
        print(f"Executing scheduling algorithm: {algo_name}")
        start_time = time.perf_counter()
        scheduler_job = self.algorithm.execute(scheduler_job, machines) if self.algorithm else scheduler_job
        end_time = time.perf_counter()

        # Step 3: Capture scheduling results
        self._capture(
            capture_result_schedule,
            scheduler_job=scheduler_job,
            machines=machines,
            start_time=start_time,
            end_time=end_time,
        )
        return scheduler_job

    def _capture(
        self,
        capture_result_schedule: Any,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, Any],
        start_time: float,
        end_time: float,
    ) -> None:
        algo_name = self.algorithm.__class__.__name__ if self.algorithm is not None else "DefaultAlgorithm"
        latency = end_time - start_time

        if hasattr(capture_result_schedule, "name_schedule"):
            capture_result_schedule.name_schedule = algo_name

        if hasattr(capture_result_schedule, "schedule_latency"):
            capture_result_schedule.schedule_latency = latency

        capture_result_schedule.exceed_cutting_policy = self.exceed_cutting_policy

        # Auto-detect whether optional cutting occurred
        max_capacity = SchedulingCutterHelper.get_max_capacity(machines)
        has_optional_cut = False
        has_shot_distribution = False
        for s_job in scheduler_job.values():
            info = getattr(s_job, "job_information", None)
            # A shot shard stands for its logical job, which may be a cut subcircuit
            if getattr(info, "shot_parent", None) is not None:
                has_shot_distribution = True
                info = info.shot_parent
            parent = getattr(info, "parent_job", None)
            if parent is not None:
                parent_qubits = getattr(parent, "num_qubits", 0) or getattr(
                    getattr(parent, "circuit", None), "num_qubits", 0
                )
                if parent_qubits <= max_capacity:
                    has_optional_cut = True

        capture_result_schedule.optional_cutting = has_optional_cut
        capture_result_schedule.shot_distribution = has_shot_distribution
        algo_policy = getattr(self.algorithm, "cutting_policy", None) or getattr(
            self.algorithm, "optional_cutting_policy", None
        )
        if has_optional_cut and not algo_policy:
            capture_result_schedule.optional_cutting_policy = "algorithm_defined"
        else:
            capture_result_schedule.optional_cutting_policy = algo_policy
