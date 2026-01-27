
from abc import ABC, abstractmethod
from typing import Any, Dict
import sys
import time

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo
from component.dataclass.job_info import TranspiledJob
from component.dataclass.job_info import ExecutionResult
from component.dataclass.result_schedule import ResultOfSchedule
from qiskit_ibm_runtime import SamplerV2
from copy import deepcopy


class ExecutionPhase(ABC):
    """
    Abstract base class for the Execution Phase.
    
    Input: Output of transpile phase (transpiled circuits)
    Output: Execution results from running circuits on quantum machines
    """
    
    @abstractmethod
    def execute(self, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], 
                transpiled_job: Dict[str, TranspiledJob], result_schedule: ResultOfSchedule) -> Dict[str, SchedulerJobInfo]:
        """
        Executes the execution phase.

        Args:
            scheduler_job: Dictionary of scheduled jobs.
            machines: Dictionary of available machines.
            transpiled_job: Dictionary of transpiled circuits.
            result_schedule: ResultOfSchedule object to update with metrics.

        Returns:
            Updated scheduler_job with execution results.
        """
        pass

class ConcreteExecutionPhase(ExecutionPhase):
    def execute(self, scheduler_job_estimate: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], 
                transpiled_job: Dict[str, TranspiledJob], result_schedule: ResultOfSchedule) -> Dict[str, SchedulerJobInfo]:
        """
        Execute transpiled circuits on their assigned machines and collect results.
        """
        scheduler_job_simulation = deepcopy(scheduler_job_estimate)
        # Create queue slot for each machine in machines
        machine_queues = {machine_name: [] for machine_name in machines.keys()}
        # Update job in scheduler_job_estimate to machine queues
        for job_name, job_info in scheduler_job_estimate.items():
            assigned_machine = job_info.assigned_machine
            machine_queues[assigned_machine].append(job_name)
        
        # When simulation each job has new duration, update start time and end time based on new duration
        # Sort all jobs by their scheduled start time to process them in order
        sorted_jobs = sorted(scheduler_job_estimate.items(), key=lambda x: x[1].scheduled_start_time)
        
        # Track current time for each machine
        machine_current_time = {machine_name: 0 for machine_name in machines.keys()}
        
        # Process jobs in order of their scheduled start time
        for job_name, job_info in sorted_jobs:
            assigned_machine = job_info.assigned_machine
            duration = transpiled_job[job_name].transpiled_circuit.duration * transpiled_job[job_name].job_information.shots
            
            # Update the job's actual start and end time based on machine availability
            actual_start = max(machine_current_time[assigned_machine], job_info.scheduled_start_time)
            scheduler_job_simulation[job_name].scheduled_start_time = actual_start
            scheduler_job_simulation[job_name].scheduled_end_time = actual_start + duration
            
            # Update machine's current time
            machine_current_time[assigned_machine] = actual_start + duration
                
                        
        # Execution on simulation machines
        for job_name, job_info in transpiled_job.items():
            job = SamplerV2(machines[job_info.machine_name]).run([job_info.transpiled_circuit], shots=job_info.job_information.shots)
            pub_result = job.result()[0]
            counts = pub_result.data.meas.get_counts()
            # print(f"Execution results for job {job_name} on machine {job_info.machine_name}: {counts}")

        # update arrival time and execution time to scheduler_job_simulation
        
        return scheduler_job_simulation
