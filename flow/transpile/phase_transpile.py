from abc import ABC, abstractmethod
from typing import Any, Dict
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo
from component.dataclass.job_info import TranspiledJob
from qiskit.compiler import transpile
import mapomatic as mm

class TranspilePhase(ABC):
    """
    Abstract base class for the Transpile Phase.
    
    Input: Output of schedule phase
    Output: Transpiled quantum circuit on quantum machine
    """ 
    
    @abstractmethod
    def execute(self, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Dict[str, TranspiledJob]:
        """
        Executes the transpile phase.

        Args:
            scheduler_job: Dictionary of scheduled jobs.
            machines: Dictionary of available machines.

        Returns:
            Updated scheduler_job with transpiled circuits.
        """
        pass

class ConcreteTranspilePhase(TranspilePhase):
    def execute(self, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], capture_result_schedule: Any) -> Dict[str, TranspiledJob]:
        transpiled_job: Dict[str, TranspiledJob] = {}
        
        for job_name, job_info in scheduler_job.items():
            transpiled_job[job_name] = TranspiledJob(job_information=job_info.job_information, machine_name=job_info.assigned_machine)
            transpiled_job_temp = transpile(job_info.job_information.circuit, machines[job_info.assigned_machine])
            layouts = mm.matching_layouts(transpiled_job_temp, machines[job_info.assigned_machine])
            scores = mm.evaluate_layouts(transpiled_job_temp, layouts, machines[job_info.assigned_machine])
            best_layout = scores[0][0]
            number_of_qubits = job_info.job_information.circuit.num_qubits
            best_layout = best_layout[0:number_of_qubits]
            print(f"Best layout for job {job_name} on machine {job_info.assigned_machine}: {best_layout}")
            transpiled_job[job_name].transpiled_circuit = transpile(job_info.job_information.circuit, machines[job_info.assigned_machine], initial_layout=best_layout, scheduling_method='alap')
        return transpiled_job