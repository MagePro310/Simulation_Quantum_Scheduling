from dataclasses import dataclass, field
from typing import Optional, Dict
from component.dataclass.job_info import SchedulerJobInfo

@dataclass
class ResultOfSchedule:
    """
    Comprehensive dataclass for storing quantum scheduling simulation results.
    Contains proxy information and various performance metrics.
    """
    
    # ========== Information of Input Phase   ==========    
    numCircuits: int = 0
    nameCircuits: str = ""
    averageQubits: float = 0.0
    nameMachines: str = ""
    
    # ========== Information of Schedule Phase   ==========    
    nameSchedule: str = ""
    ScheduleLatency: float = 0.0

    # ========== Performance Metrics (Hiệu suất) ==========
    # Thời gian thực thi
    makespan: float = 0.0  # Tổng thời gian để hoàn thành tất cả các job trong workload
    totalTurnaroundTime: float = 0.0  # Tổng thời gian từ khi submit job đến khi job hoàn thành
    totalWaitingTime: float = 0.0  # Tổng thời gian job phải chờ trong queue trước khi bắt đầu thực thi
    totalResponseTime: float = 0.0  # Tổng thời gian từ khi submit đến khi job bắt đầu được thực thi
    averageTurnaroundTime: float = 0.0  # Thời gian trung bình từ khi submit job đến khi job hoàn thành
    averageWaitingTime: float = 0.0  # Thời gian trung bình job phải chờ trong queue trước khi bắt đầu thực thi
    averageResponseTime: float = 0.0  # Thời gian trung bình từ khi submit đến khi job bắt đầu được thực thi    
    jobCompletionRate: float = 0.0  # Tỷ lệ job hoàn thành trên đơn vị thời gian
    
    # ========== Quantum-Specific Metrics ==========
    averageFidelity: float = 0.0  # Độ chính xác trung bình của quantum circuit

    def calculate_metrics(self, scheduler_job: Dict[str, SchedulerJobInfo]):
        """
        Calculates and updates performance metrics based on the scheduled jobs.
        
        Args:       
            scheduler_job: Dictionary of SchedulerJobInfo objects containing scheduling details.
        """
        makespan = 0.0
        total_turnaround_time = 0.0
        total_waiting_time = 0.0
        total_response_time = 0.0
        num_jobs = len(scheduler_job)

        if num_jobs > 0:
            for job_name, s_job in scheduler_job.items():
                arrival_time = s_job.job_information.arrival_time if s_job.job_information.arrival_time is not None else 0.0
                
                # Makespan is the max end time
                if s_job.scheduled_end_time > makespan:
                    makespan = s_job.scheduled_end_time
                
                # Turnaround Time = Completion Time - Arrival Time
                turnaround_time = s_job.scheduled_end_time - arrival_time
                total_turnaround_time += turnaround_time
                
                # Waiting Time = Start Time - Arrival Time
                waiting_time = s_job.scheduled_start_time - arrival_time
                total_waiting_time += waiting_time
                
                # Response Time = First Start Time - Arrival Time
                response_time = s_job.scheduled_start_time - arrival_time
                total_response_time += response_time

            self.makespan = makespan
            self.totalTurnaroundTime = total_turnaround_time
            self.totalWaitingTime = total_waiting_time
            self.totalResponseTime = total_response_time
            self.averageTurnaroundTime = total_turnaround_time / num_jobs
            self.averageWaitingTime = total_waiting_time / num_jobs
            self.averageResponseTime = total_response_time / num_jobs
            self.jobCompletionRate = num_jobs / makespan
