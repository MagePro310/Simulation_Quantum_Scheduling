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
    partition_label: str | None = None
    subexperiments: list[QuantumCircuit] | None = None
    cutting_context: object | None = None
    cutting_overhead: float = 0.0
        
@dataclass
class SchedulerJobInfo:
    """
    Class to store scheduler job information.
    """

    job_information: JobInfo | None = None
    assigned_machine: str | None = None
    dispatch_order: int | None = None
    depends_on: list[JobInfo | None] | None = None # run after these jobs are completed
    
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
    hellinger_fidelity: float | None = None
    tvd: float | None = None
    bhattacharyya_fidelity: float | None = None
    uncut_distribution: dict[str, int] | None = None
    reconstructed_distribution: dict[str, int] | None = None
    cutting_overhead: float = 0.0
    start_time: float | None = None
    end_time: float | None = None
    execution_time: float | None = None
    status: str = "PENDING"
    error_reason: str | None = None
    requested_shots: int = 0
    completed_shots: int = 0
    
