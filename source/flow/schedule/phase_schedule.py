import sys
from typing import Any, Dict
import time

# Add the project root to sys.path if not already there
sys.path.append('./')

from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.flow.schedule.main_schedule_algorithm import MainScheduleAlgorithm
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo


class ConcreteSchedulePhase:
    """Orchestrates pre-schedule circuit preparation (mandatory exceed + optional) and scheduling."""

    def __init__(
        self,
        algorithm: Any = None,
        exceed_cutting_policy: str = "greedy",
        enable_optional_cutting: bool = False,
        optional_cutting_policy: str = "half",
    ):
        self.algorithm = algorithm
        self.exceed_cutting_policy = exceed_cutting_policy.lower()
        self.enable_optional_cutting = enable_optional_cutting
        self.optional_cutting_policy = optional_cutting_policy.lower()

        self.pre_phase = PreSchedulePhase(
            exceed_cutting_policy=self.exceed_cutting_policy,
            enable_optional_cutting=self.enable_optional_cutting,
            optional_cutting_policy=self.optional_cutting_policy,
        )
        self.main_schedule_algorithm = MainScheduleAlgorithm()

    def set_exceed_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy for oversized circuits: 'greedy' or 'half'."""
        self.exceed_cutting_policy = policy.lower()
        self.pre_phase.set_exceed_cutting_policy(self.exceed_cutting_policy)

    def set_optional_cutting(self, enable: bool = True, policy: str = "half") -> None:
        """Configure optional cutting stage."""
        self.enable_optional_cutting = enable
        self.optional_cutting_policy = policy.lower()
        self.pre_phase.set_optional_cutting(enable=enable, policy=self.optional_cutting_policy)

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any],
        capture_result_schedule: Any,
    ) -> Dict[str, SchedulerJobInfo]:
        """Execute pre-scheduling cutting (mandatory + optional) and the chosen algorithm.

        Args:
            origin_job_info: Original input circuits.
            machines: Target machine specifications.
            capture_result_schedule: Dataclass to record scheduling metadata.

        Returns:
            Dictionary of SchedulerJobInfo with assignments and dispatch orders.
        """
        # Step 1: Pre-phase prepares circuits (Stage 1: mandatory exceed cut, Stage 2: optional cut)
        scheduler_job = self.pre_phase.execute(origin_job_info, machines)

        # Step 2: Main schedule algorithm executes
        algo_name = self.algorithm.__class__.__name__ if self.algorithm is not None else "DefaultAlgorithm"
        print(f"Executing scheduling algorithm: {algo_name}")
        start_time = time.perf_counter()
        scheduler_job = self.main_schedule_algorithm.execute(self.algorithm, scheduler_job, machines)
        end_time = time.perf_counter()

        # Step 3: Capture scheduling results
        self._capture(capture_result_schedule, scheduler_job, start_time, end_time)
        return scheduler_job

    def _capture(
        self,
        capture_result_schedule: Any,
        scheduler_job: Dict[str, SchedulerJobInfo],
        start_time: float,
        end_time: float,
    ) -> None:
        capture_result_schedule.nameSchedule = (
            self.algorithm.__class__.__name__ if self.algorithm is not None else "DefaultAlgorithm"
        )
        capture_result_schedule.ScheduleLatency = end_time - start_time
        capture_result_schedule.exceed_cutting_policy = self.exceed_cutting_policy
        capture_result_schedule.optional_cutting = self.enable_optional_cutting
        capture_result_schedule.optional_cutting_policy = (
            self.optional_cutting_policy if self.enable_optional_cutting else None
        )

