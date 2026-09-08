from dataclasses import dataclass
# Qiskit 2.3 does not ship typing metadata or stubs.
from qiskit import QuantumCircuit  # pyright: ignore[reportMissingTypeStubs]

@dataclass
class JobInfo:
    """
    Class to store job information.
    """
    # Basic information
    job_name: str | None = None
    circuit: QuantumCircuit | None = None
    num_qubits: int | None = None
    shots: int | None = None

    # Help for scheduler
    arrival_time: float | None = None
    priority: int | None = None
    
    # Help for cut
    parentJob: 'JobInfo | None' = None
    childrenJobs: dict[str, 'JobInfo'] | None = None
        
@dataclass
class SchedulerJobInfo:
    """
    Class to store scheduler job information.
    """

    job_information: JobInfo | None = None
    assigned_machine: str | None = None
    dispatch_order: int | None = None
    depends_on: list[JobInfo | None] | None = None # run after these jobs are completed
    
# @dataclass
# class TranspiledJob:
#     job_information: JobInfo | None = None
#     machine_name: str | None = None
#     transpiled_circuit: QuantumCircuit | None = None
#     physical_layout: list[int] | None = None
    
# @dataclass
# class TranspiledJobInfo:
#     job_info: List[JobInfo] 
#     merged_circuit: QuantumCircuit
#     transpiled_circuit: QuantumCircuit

    
@dataclass
class ExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    job_info: JobInfo
    assigned_machine: str | None = None
    distribution_no_noise: dict[str, int] | None = None
    distribution_with_noise: dict[str, int] | None = None
    fidelity: float | None = None
    start_time: float | None = None
    end_time: float | None = None
    execution_time: float | None = None

# @dataclass
# class MachineExecutionResult:
#     """
#     Class to store execution results for a quantum job.
#     """
#     machine_name: str
#     utilization: float | None = None

# @dataclass
# class MainExecutionResult:
#     """
#     Class to store execution results for a quantum job.
#     """
#     job_info: List[JobInfo]
#     distribution_no_noise: Dict[str, int] | None = None
#     distribution_with_noise: Dict[str, int] | None = None
#     execution_time: float | None = None
    
# @dataclass
# class Total_analysis_result:
#     """
#     Class to store execution results for a quantum job.
#     """
#     makespan_on_all_machines: float | None = None
#     average_execution_time_per_machines: Dict[str, float] | None = None
#     average_utilization_per_machines: Dict[str, float] | None = None
#     average_fidelity_of_all_jobs: float | None = None
    