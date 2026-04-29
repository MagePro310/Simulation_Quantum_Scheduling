from typing import Any, Dict
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo
from flow.schedule.estimated import estimated_schedule

class FFD:
    """
    First Fit Decreasing (FFD) Algorithm for Quantum Job Scheduling.
    
    This algorithm schedules quantum circuits (jobs) onto quantum machines based on:
    - Job priority: Sorted by circuit size (number of qubits) in decreasing order
    - Machine availability: Each job assigned to machine with earliest completion time
    
    Algorithm steps:
    1. Sort jobs in decreasing order by circuit size (number of qubits)
    2. For each job, assign it to the machine that becomes available soonest
    3. Schedule job to start when assigned machine finishes current workload
    """
    
    @staticmethod
    def execute(scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any]) -> Dict[str, SchedulerJobInfo]:
        """
        Execute the FFD scheduling algorithm.
        
        Args:
            scheduler_job: Dictionary of SchedulerJobInfo objects with job name as key
            machines: Dictionary of quantum machine backends with machine name as key
            
        Returns:
            Updated scheduler_job dictionary with assigned machines and scheduled times
        """
        # Step 1: Sort jobs by circuit size (number of qubits) in decreasing order
        sorted_jobs = sorted(
            scheduler_job.items(),
            key=lambda item: item[1].job_information.circuit.num_qubits,
            reverse=True
        )
        
        # Step 2: Initialize machine tracking (only track when each machine becomes free)
        machine_current_time = {machine_name: 0.0 for machine_name in machines.keys()}
        
        # Step 3: Assign each job to the machine with earliest availability
        for job_name, job_info in sorted_jobs:
            circuit = job_info.job_information.circuit
            
            # Find the machine that will be free soonest
            # (First Fit Decreasing: assign to first available machine in iteration order)
            earliest_machine = None
            earliest_time = float('inf')
            
            for machine_name, machine_backend in machines.items():
                if machine_current_time[machine_name] < earliest_time:
                    earliest_time = machine_current_time[machine_name]
                    earliest_machine = machine_name
            
            # Assign the job to the earliest available machine
            job_info.assigned_machine = earliest_machine
            
            # Set scheduled times
            job_info.scheduled_start_time = machine_current_time[earliest_machine]
            
            # Estimate execution time using the estimation function
            execution_time = estimated_schedule(circuit, shots=1024)
            job_info.scheduled_end_time = job_info.scheduled_start_time + execution_time
            
            # Update machine's completion time
            machine_current_time[earliest_machine] = job_info.scheduled_end_time
        
        return scheduler_job
