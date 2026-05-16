from abc import ABC, abstractmethod
import re
import sched
from typing import Any, Dict, Tuple
import time
import sys
from copy import deepcopy

from flow.schedule.post_schedule import PostSchedulePhase
from flow.schedule.pre_schedule import PreSchedulePhase
from flow.schedule.main_schedule_algorithm import MainScheduleAlgorithm
# Add the project root to sys.path if not already there
sys.path.append('./')
from collections import defaultdict
from component.dataclass.job_info import JobInfo, SchedulerJobInfo
from algorithm.heuristic.FFD import FFD
from component.dataclass.job_info import SchedulerJobInfo, TranspiledJob

    
class ConcreteSchedulePhase():
    def __init__(self):
        self.pre_phase = PreSchedulePhase()
        self.main_schedule_algorithm = MainScheduleAlgorithm()
        self.post_phase = PostSchedulePhase()

    def capture(self, capture_result_schedule: Any, scheduler_job: Dict[str, SchedulerJobInfo], start_time: float, end_time: float):
        capture_result_schedule.nameSchedule = "FFD"
        capture_result_schedule.ScheduleLatency = end_time - start_time
        capture_result_schedule.calculate_metrics(scheduler_job)
        
    
    def execute(self, origin_job_info: Dict[str, JobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo]]:
        # Process job info and cut the circuits if needed
        scheduler_job = self.pre_phase.execute(origin_job_info)
        
        start_time = time.time() 
        scheduler_job = self.main_schedule_algorithm.base_schedule_algorithm(scheduler_job, machines)
        end_time = time.time()
        self.capture(capture_result_schedule, scheduler_job, start_time, end_time)
        execution_job_relations = self.post_phase.execute(scheduler_job, machines)  
        return execution_job_relations
