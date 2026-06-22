import sys
sys.path.append('./')
from dataclasses import dataclass
from typing import Any, Dict, List

from component.dataclass.job_info import JobInfo, TranspiledJobInfo
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import SamplerV2
from component.dataclass.job_info import MainExecutionResult

class MainExecutionQuantum:
    def execute(
        self,
        machines: Dict[str, Any],
        transpiled_job: Dict[str, List[TranspiledJobInfo]],
    ) -> Dict[str, List[MainExecutionResult]]:
        """Simulate the execution of the schedule on the quantum machine."""
        backend = AerSimulator()
        executionresult: Dict[str, List[MainExecutionResult]] = {}
        for machine_name, transpiled_jobs in transpiled_job.items():
            executionresult[machine_name] = []
            for transpiled_job_info in transpiled_jobs:
                # Simulate the execution of the transpiled circuit
                execution_time = transpiled_job_info.transpiled_circuit.duration
                shots = transpiled_job_info.job_info[0].shots
                result_no_noise = backend.run(transpiled_job_info.transpiled_circuit, shots=shots).result()
                distribution_no_noise = result_no_noise.get_counts()
                
                sampler = SamplerV2(machines[machine_name])
                pub_result = sampler.run([transpiled_job_info.transpiled_circuit], shots=shots).result()[0]
                distribution_with_noise = pub_result.data.meas.get_counts()
                
                executionresult[machine_name].append(
                    MainExecutionResult(
                        job_info=transpiled_job_info.job_info,
                        distribution_no_noise=distribution_no_noise,
                        distribution_with_noise=distribution_with_noise,
                        execution_time=execution_time,
                    )
                )

        print("Completed execution on all machines.")
        return executionresult
