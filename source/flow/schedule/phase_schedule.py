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
    def __init__(self, algorithm: Any = None):
        self.algorithm = algorithm
        
        self.pre_phase = PreSchedulePhase()
        self.main_schedule_algorithm = MainScheduleAlgorithm()

    def execute(self, origin_job_info: Dict[str, JobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Dict[str, SchedulerJobInfo]:
        # Process job info and cut the circuits if needed
        # pre_phase: TODO implement circuit cutting if nessessary
        scheduler_job = self.pre_phase.execute(origin_job_info)
        
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
