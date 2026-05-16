from collections import defaultdict
from unittest import result

from pyparsing import Dict
from copy import deepcopy
from typing import Any, Tuple, Dict
import sys
from component.dataclass.job_info import SchedulerJobInfo, SchedulerJobInfo, TranspiledJob, TranspiledJob

class PostSchedulePhase():
    def execute(self, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any]) -> Dict[str, Any]:
        machine_map = defaultdict(list)
        
        for job_key, job_info in scheduler_job.items():
            machine_map[job_info.assigned_machine].append(job_info)
            
        result  = {}
        for machine, jobs in machine_map.items():
            timestamps = set()
            for job in jobs:
                timestamps.add(job.scheduled_start_time)
                timestamps.add(job.scheduled_end_time)
            
            sorted_times = sorted(list(timestamps))
            machine_intervals = []
            for i in range(len(sorted_times) - 1):
                t_start = sorted_times[i]
                t_end = sorted_times[i+1]
                
                active_jobs = [
                    job.job_information
                    for job in jobs 
                    if job.scheduled_start_time <= t_start and job.scheduled_end_time >= t_end
                ]
                
                if active_jobs and (not machine_intervals or machine_intervals[-1] != active_jobs):
                    machine_intervals.append(active_jobs)

            result[machine] = machine_intervals
        return result