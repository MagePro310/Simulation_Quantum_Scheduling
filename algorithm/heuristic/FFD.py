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
    - Circuit size: number of qubits required by the circuit
    - Machine capacity: number of qubits available on the machine
    
    Algorithm steps:
    1. Sort jobs in decreasing order by circuit size (number of qubits)
    2. For each job, assign it to the first machine that has enough capacity
    3. Track the current load on each machine to ensure capacity constraints
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
        
        # Step 2: Initialize machine tracking
        machine_current_time = {machine_name: 0.0 for machine_name in machines.keys()}
        machine_used_qubits = {machine_name: 0 for machine_name in machines.keys()}
        
        # Step 3: Assign each job to the first fitting machine
        for job_name, job_info in sorted_jobs:
            circuit = job_info.job_information.circuit
            circuit_qubits = circuit.num_qubits
            
            # Find the first machine that can accommodate this circuit
            assigned = False
            for machine_name, machine_backend in machines.items():
                machine_capacity = machine_backend.num_qubits
                current_load = machine_used_qubits[machine_name]
                
                # Check if the machine has enough qubits for this circuit
                if circuit_qubits + current_load <= machine_capacity:
                    # Assign the job to this machine
                    job_info.assigned_machine = machine_name
                    
                    # Set scheduled times (simple sequential scheduling on each machine)
                    job_info.scheduled_start_time = machine_current_time[machine_name]
                    
                    # Estimate execution time (simplified: assume 1 time unit per gate)
                    # You can replace this with a more sophisticated estimation
                    
                    execution_time = estimated_schedule(circuit, shots=1024)  # Example: using 1024 shots for estimation
                    job_info.scheduled_end_time = job_info.scheduled_start_time + execution_time
                    
                    # Update machine's current time
                    machine_current_time[machine_name] = job_info.scheduled_end_time
                    machine_used_qubits[machine_name] += circuit_qubits
                    
                    assigned = True
                    break
            
            # If no machine can accommodate this job, raise an error
            if not assigned:
                raise ValueError(
                    f"Job '{job_name}' requires {circuit_qubits} qubits, "
                    f"but no machine has sufficient remaining capacity. "
                    f"Machine usage: {[(name, machine_used_qubits[name], backend.num_qubits) for name, backend in machines.items()]}"
                )
        
        return scheduler_job
