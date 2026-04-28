from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple
import time
import sys
from copy import deepcopy


# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import JobInfo, SchedulerJobInfo
from algorithm.heuristic.FFD import FFD

class BaseSchedulePhase(ABC):
    """
    Abstract base class for the Schedule Phase.
    
    Input: Output of input phase
    Output: Order of quantum circuit on quantum machine
    """
    
    @abstractmethod
    def execute(self, origin_job_info: Dict[str, JobInfo], machines: Dict[str, Any], scheduler_job: SchedulerJobInfo, capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo], Any, Any]:
        """
        Executes the schedule phase.

        Args:
            origin_job_info: Dictionary of original jobs.
            machines: Dictionary of available machines.
            result_Schedule: ResultOfSchedule object.

        Returns:
            A tuple containing:
            - Updated scheduler_job (with schedule info).
            - Loaded data from schedule.json.
            - Updated result_Schedule object.
        """
        pass

class ConcreteSchedulePhase(BaseSchedulePhase):
    def execute(self, origin_job_info: Dict[str, JobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo], Any, Any]:
        # Process job info and cut the circuits if needed

        # Update origin_job_info to scheduler_job
        scheduler_job: Dict[str, SchedulerJobInfo] = {}
        for job_name, job_info in origin_job_info.items():
            scheduler_job[job_name] = SchedulerJobInfo(job_information=deepcopy(job_info))
        
        start_time = time.time()
        # Use FFD algorithm to schedule jobs on machines
        scheduler_job = FFD.execute(scheduler_job, machines)
        end_time = time.time()

        # capture
        capture_result_schedule.nameSchedule = "FFD"
        capture_result_schedule.ScheduleLatency = end_time - start_time
        # Calculate Metrics
        capture_result_schedule.calculate_metrics(scheduler_job)

        return scheduler_job

    