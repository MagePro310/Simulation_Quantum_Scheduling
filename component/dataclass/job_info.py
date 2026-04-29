from dataclasses import dataclass
from qiskit import QuantumCircuit
from typing import Dict, Any
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
class JobExecutionRelation:
    """
    Unified job payload passed into execution.

    Contains:
    - scheduling metadata (`scheduler_job`)
    - transpilation metadata (`transpiled_job`)
    - machine-local predecessor/successor links
    """
    job_name: str
    machine_name: str
    scheduler_job: SchedulerJobInfo
    transpiled_job: TranspiledJob | None = None
    prev_job_on_machine: str | None = None
    next_job_on_machine: str | None = None
    
@dataclass
class ExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    job_name: str
    counts: Dict[str, int] | None = None
    quasi_probs: Dict[str, float] | None = None
    fidelity: float | None = None
    execution_time: float | None = None
    shots: int = 1024
    metadata: Dict[str, Any] | None = None