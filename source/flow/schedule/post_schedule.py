from collections import defaultdict
from types import SimpleNamespace
from typing import Any, Dict

from source.component.dataclass.job_info import SchedulerJobInfo
from source.component.visualize.gantt_chart import GanttChart

class PostSchedulePhase():
    def execute(
        self,
        scheduler_job: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        output_path: str = "schedule_gantt_chart.png",
    ) -> Dict[str, Any]:
        print("PostSchedule: Grouping jobs by machine and execution intervals...")
        gantt_input = {
            job_name: SimpleNamespace(
                assigned_machine=job.assigned_machine,
                scheduled_start_time=job.scheduled_start_time,
                scheduled_end_time=job.scheduled_end_time,
                num_qubits=getattr(getattr(job.job_information, "circuit", None), "num_qubits", None),
                shots=getattr(job.job_information, "shots", None),
            )
            for job_name, job in scheduler_job.items()
        }
        GanttChart().display(gantt_input, machines, output_path=output_path)

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