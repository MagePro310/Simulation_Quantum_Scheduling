from dataclasses import dataclass
from numpy import average
from qiskit import QuantumCircuit
from typing import Dict, Any, List
# from component.c_circuit_work.cutting.width_c import SubCircuitInfo

@dataclass
class JobInfo:
    """
    Class to store job information.
    """
    # Basic information
    job_name: str = None
    circuit: QuantumCircuit = None
    shots: int = None

    # Help for scheduler
    arrival_time: float = None
    priority: int = None
    
    # Help for cut
    parentJob: 'JobInfo' = None
    childrenJobs: dict[str, 'JobInfo'] = None
        
@dataclass
class SchedulerJobInfo:
    """
    Class to store scheduler job information.
    """

    job_information: JobInfo = None
    scheduled_start_time: float = 0
    scheduled_end_time: float = 0
    assigned_machine: str = None
    
@dataclass
class TranspiledJob:
    job_information: JobInfo = None
    machine_name: str | None = None
    transpiled_circuit: QuantumCircuit | None = None
    physical_layout: list[int] | None = None
    
@dataclass
class TranspiledJobInfo:
    job_info: List[JobInfo] 
    merged_circuit: QuantumCircuit
    transpiled_circuit: QuantumCircuit

    
@dataclass
class ExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    job_info: JobInfo
    assigned_machine: str | None = None
    distribution_no_noise: Dict[str, int] | None = None
    distribution_with_noise: Dict[str, int] | None = None
    fidelity: float | None = None
    start_time: float | None = None
    end_time: float | None = None
    execution_time: float | None = None

@dataclass
class MachineExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    machine_name: str
    utilization: float | None = None

@dataclass
class MainExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    job_info: List[JobInfo]
    distribution_no_noise: Dict[str, int] | None = None
    distribution_with_noise: Dict[str, int] | None = None
    execution_time: float | None = None
    
@dataclass
class Total_analysis_result:
    """
    Class to store execution results for a quantum job.
    """
    makespan_on_all_machines: float | None = None
    average_execution_time_per_machines: Dict[str, float] | None = None
    average_utilization_per_machines: Dict[str, float] | None = None
    average_fidelity_of_all_jobs: float | None = None
    