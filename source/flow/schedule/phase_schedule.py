import sys
from typing import Any, Dict
import time

# Add the project root to sys.path if not already there
sys.path.append('./')

from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.flow.schedule.main_schedule_algorithm import MainScheduleAlgorithm
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo


class ConcreteSchedulePhase:
    """Orchestrates pre-schedule circuit preparation and scheduling algorithms."""

    def __init__(
        self,
        algorithm: Any = None,
        cutting_policy: str = "greedy",
        **kwargs: Any,
    ):
        self.algorithm = algorithm
        self.cutting_policy = cutting_policy.lower()
        self.pre_phase = PreSchedulePhase(cutting_policy=self.cutting_policy)
        self.main_schedule_algorithm = MainScheduleAlgorithm()

    def set_cutting_policy(self, policy: str) -> None:
        """Set mandatory cutting policy: 'greedy' or 'half'."""
        self.cutting_policy = policy.lower()
        self.pre_phase.set_cutting_policy(self.cutting_policy)

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any],
        capture_result_schedule: Any,
    ) -> Dict[str, SchedulerJobInfo]:
        """Execute pre-scheduling cutting and the chosen scheduling algorithm.

        Args:
            origin_job_info: Original input circuits.
            machines: Target machine specifications.
            capture_result_schedule: Dataclass to record scheduling metadata.

        Returns:
            Dictionary of SchedulerJobInfo with assignments and dispatch orders.
        """
        # Step 1: Pre-phase ensures hardware feasibility (cuts circuits > max_capacity)
        scheduler_job = self.pre_phase.execute(origin_job_info, machines)

        # Step 2: Main schedule algorithm executes (may perform autonomous cutting, e.g. FFD_v2)
        algo_name = self.algorithm.__class__.__name__ if self.algorithm is not None else "DefaultAlgorithm"
        print(f"Executing scheduling algorithm: {algo_name}")
        start_time = time.time()
        scheduler_job = self.main_schedule_algorithm.execute(self.algorithm, scheduler_job, machines)
        end_time = time.time()

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
        capture_result_schedule.cutting_policy = self.cutting_policy
