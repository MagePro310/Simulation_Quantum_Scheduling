from abc import ABC, abstractmethod
from typing import Any, Dict
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo
from component.dataclass.job_info import TranspiledJob
from component.dataclass.job_info import JobExecutionRelation
from qiskit.compiler import transpile
import mapomatic as mm

class BaseTranspilePhase(ABC):
    """
    Abstract base class for the Transpile Phase.
    
    Input: Output of schedule phase
    Output: Transpiled quantum circuit on quantum machine
    """ 
    
    @abstractmethod
    def execute(
        self,
        machines: Dict[str, Any],
        capture_result_schedule: Any,
        execution_job_relations: Dict[str, JobExecutionRelation] | None = None,
    ) -> Dict[str, TranspiledJob]:
        """
        Executes the transpile phase.

        Args:
            scheduler_job: Dictionary of scheduled jobs.
            machines: Dictionary of available machines.
            execution_job_relations: Optional execution relation map.
                If provided, transpilation is driven by this structure and
                generated `TranspiledJob` objects are written back into it.

        Returns:
            Updated scheduler_job with transpiled circuits.
        """
        pass

class ConcreteTranspilePhase(BaseTranspilePhase):
    def execute(
        self,
        machines: Dict[str, Any],
        capture_result_schedule: Any,
        execution_job_relations: Dict[str, JobExecutionRelation] | None = None,
    ) -> Dict[str, TranspiledJob]:
        transpiled_job: Dict[str, TranspiledJob] = {}

        if execution_job_relations is not None:
            transpile_inputs = {
                job_name: relation.scheduler_job
                for job_name, relation in execution_job_relations.items()
                if relation.scheduler_job is not None
            }

        for job_name, job_info in transpile_inputs.items():
            machine_name = job_info.assigned_machine
            if execution_job_relations is not None and job_name in execution_job_relations:
                machine_name = execution_job_relations[job_name].machine_name or machine_name

            transpiled_job[job_name] = TranspiledJob(
                job_information=job_info.job_information,
                machine_name=machine_name,
            )

            transpiled_job_temp = transpile(job_info.job_information.circuit, machines[machine_name])
            layouts = mm.matching_layouts(transpiled_job_temp, machines[machine_name])
            scores = mm.evaluate_layouts(transpiled_job_temp, layouts, machines[machine_name])
            
            best_layout = scores[0][0]
            number_of_qubits = job_info.job_information.circuit.num_qubits
            best_layout = best_layout[0:number_of_qubits]
            
            transpiled_job[job_name].physical_layout = best_layout
            transpiled_job[job_name].transpiled_circuit = transpile(
                job_info.job_information.circuit,
                machines[machine_name],
                initial_layout=best_layout,
                scheduling_method='alap',
            )

            if execution_job_relations is not None and job_name in execution_job_relations:
                execution_job_relations[job_name].transpiled_job = transpiled_job[job_name]
            
        return transpiled_job