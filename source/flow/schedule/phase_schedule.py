import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from typing import Any, Dict
import time

from source.flow.schedule.pre_schedule import PreSchedulePhase
from source.flow.schedule.main_schedule_algorithm import MainScheduleAlgorithm

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
    
class ConcreteSchedulePhase():
    """Schedule quantum circuits on available machines."""
    def __init__(
        self,
        algorithm: Any = None,
        cutting_policy: str = "greedy",
        cutting_scope: str = "exceed",
        cut_all: bool | None = None,
    ):
        self.algorithm = algorithm
        self.cutting_policy = cutting_policy.lower()
        if cut_all is not None:
            self.cutting_scope = "all" if cut_all else "exceed"
        else:
            self.cutting_scope = cutting_scope.lower()
        
        self.pre_phase = PreSchedulePhase(
            cutting_policy=self.cutting_policy,
            cutting_scope=self.cutting_scope,
        )
        self.main_schedule_algorithm = MainScheduleAlgorithm()

    def set_cutting_scope(self, scope: str) -> None:
        """Option function to set cutting scope: 'all' or 'exceed'."""
        self.cutting_scope = scope.lower()
        self.pre_phase.set_cutting_scope(self.cutting_scope)

    def set_cut_all(self, cut_all: bool = True) -> None:
        """Option function to toggle cutting all circuits (True) vs only exceeding capacity (False)."""
        self.set_cutting_scope("all" if cut_all else "exceed")

    def set_cutting_policy(self, policy: str) -> None:
        """Option function to set cutting policy: 'greedy' or 'half'."""
        self.cutting_policy = policy.lower()
        self.pre_phase.set_cutting_policy(self.cutting_policy)

    def configure_cutting(
        self,
        policy: str | None = None,
        scope: str | None = None,
        cut_all: bool | None = None,
    ) -> None:
        """Option function to configure circuit cutting policy and scope."""
        if policy is not None:
            self.set_cutting_policy(policy)
        if cut_all is not None:
            self.set_cut_all(cut_all)
        elif scope is not None:
            self.set_cutting_scope(scope)

    def execute(self, origin_job_info: Dict[str, JobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Dict[str, SchedulerJobInfo]:
        # Process job info and cut the circuits if needed
        # pre_phase: implement circuit cutting if necessary
        scheduler_job = self.pre_phase.execute(origin_job_info, machines)
        
        # main_schedule_algorithm: Schedule the jobs on the machines using the specified algorithm
        print(f"Executing scheduling algorithm: {self.algorithm.__class__.__name__ if self.algorithm is not None else 'DefaultAlgorithm'}")
        start_time = time.time() 
        scheduler_job = self.main_schedule_algorithm.execute(self.algorithm, scheduler_job, machines)
        end_time = time.time()
        
        # Capture the scheduling results
        self._capture(capture_result_schedule, scheduler_job, start_time, end_time)
        return scheduler_job

    def _capture(self, capture_result_schedule: Any, scheduler_job: Dict[str, SchedulerJobInfo], start_time: float, end_time: float):
        capture_result_schedule.nameSchedule = self.algorithm.__class__.__name__ if self.algorithm is not None else "DefaultAlgorithm"
        capture_result_schedule.ScheduleLatency = end_time - start_time
        capture_result_schedule.cutting_policy = self.cutting_policy
        capture_result_schedule.cutting_scope = self.cutting_scope

