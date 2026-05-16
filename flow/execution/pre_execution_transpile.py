
from ctypes import sizeof
from heapq import merge
from platform import machine
import re
from typing import Any, Dict, List

from copy import deepcopy

from component.dataclass import job_info
from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *

from qiskit.compiler import transpile

#  THis
@dataclass
class TranspiledJobInfo:
    job_info: List[JobInfo] 
    merged_circuit: QuantumCircuit
    transpiled_circuit: QuantumCircuit

class PreExecution:
    def compose(self, circuits: List[Any]) -> Any:
        if len(circuits) == 1:
            return circuits[0].circuit
        else:
            # Merge all circuits by tensoring them together
            return_circuit = circuits[0].circuit
            for i in range(1, len(circuits)):
                return_circuit = circuits[i].circuit.tensor(return_circuit)
            return return_circuit
        

    def transpile_jobs(self, machines: Dict[str, Any], execution_job_relations: Dict[str, JobInfo] | None,
    ) -> Dict[str, List[QuantumCircuit]]:
        """Transpile jobs and attach physical layout + transpiled circuit when possible."""
        print("Starting transpilation of jobs...")
        # This return dict machine_name -> list of circuit, and transpiled circuit
        transpiled_job: Dict[str, List[TranspiledJobInfo]] = {}
        
        circuit_on_machines: Dict[str, List[QuantumCircuit]] = {}
        for machine_name, job_info in execution_job_relations.items():
            transpiled_job[machine_name] = []
            circuit_on_machines[machine_name] = []
        
        for machine_name, job_info in execution_job_relations.items():
            for job in job_info:
                returncircuit = self.compose(job)
                transpiled_circuit = transpile(returncircuit, backend=machines[machine_name])
                transpiled_job[machine_name].append(TranspiledJobInfo(job_info=job, merged_circuit=returncircuit, transpiled_circuit=transpiled_circuit))
                circuit_on_machines[machine_name].append(returncircuit)
        print("Transpilation of jobs complete.")
        
        print(transpiled_job)

        # for machine_name, circuits in circuit_on_machines.items():
        #     transpiled_job[machine_name] = []
        #     for circuit in circuits:
        #         transpiled_circuit = transpile(circuit, backend=machines[machine_name])
        #         transpiled_job[machine_name].append(TranspiledJobInfo(job_info=[job], merged_circuit=transpiled_circuit)) 
        
        return transpiled_job