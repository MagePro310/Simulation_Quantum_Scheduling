import sys
sys.path.append('./')

from typing import Any, Dict, List

from component.dataclass.job_info import JobInfo, TranspiledJobInfo

from qiskit.circuit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.compiler import transpile

class PreExecution:
    def compose(self, circuits: List[Any]) -> Any:
        if not circuits:
            raise ValueError("At least one circuit is required.")

        total_qubits = sum(job.circuit.num_qubits for job in circuits)
        total_clbits = sum(job.circuit.num_clbits for job in circuits)

        registers = [QuantumRegister(total_qubits, "q")]
        if total_clbits:
            registers.append(ClassicalRegister(total_clbits, "meas"))
        merged_circuit = QuantumCircuit(*registers)

        qubit_offset = 0
        clbit_offset = 0
        for job in circuits:
            circuit = job.circuit
            merged_circuit.compose(
                circuit,
                qubits=range(qubit_offset, qubit_offset + circuit.num_qubits),
                clbits=range(clbit_offset, clbit_offset + circuit.num_clbits),
                inplace=True,
            )
            qubit_offset += circuit.num_qubits
            clbit_offset += circuit.num_clbits

        return merged_circuit
        

    def transpile_jobs(self, machines: Dict[str, Any], execution_job_relations: Dict[str, JobInfo] | None,
    ) -> Dict[str, List[TranspiledJobInfo]]:
        """Transpile jobs and attach physical layout + transpiled circuit when possible."""
        print("PreExecution: Transpiling jobs for each machine...")
        # This return dict machine_name -> list of circuit, and transpiled circuit
        transpiled_job: Dict[str, List[TranspiledJobInfo]] = {}
        
        for machine_name, job_info in execution_job_relations.items():
            transpiled_job[machine_name] = []
        
        for machine_name, job_info in execution_job_relations.items():
            for job in job_info:
                returncircuit = self.compose(job)
                transpiled_circuit = transpile(returncircuit, backend=machines[machine_name], scheduling_method='alap')
                transpiled_job[machine_name].append(TranspiledJobInfo(job_info=job, merged_circuit=returncircuit, transpiled_circuit=transpiled_circuit))
        
        return transpiled_job