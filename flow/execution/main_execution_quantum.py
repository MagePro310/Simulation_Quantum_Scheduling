
from math import dist
from platform import machine
from typing import Any, Dict, List
from copy import deepcopy

from component.dataclass import job_info
from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import SamplerV2

@dataclass
class ExecutionResult:
    """
    Class to store execution results for a quantum job.
    """
    job_info: List[JobInfo]
    distribution_no_noise: Dict[str, int] | None = None
    distribution_with_noise: Dict[str, int] | None = None
    execution_time: float | None = None

class MainExecutionQuantum:
    def execute(self, machines: Dict[str, Any], transpiled_job: Dict[str, List[TranspiledJobInfo]]):
        """Simulate the execution of the schedule on the quantum machine."""
        backend = AerSimulator()
        executionresult: Dict[str, List[ExecutionResult]] = {}
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
                
                executionresult[machine_name].append(ExecutionResult(
                    job_info=transpiled_job_info.job_info,
                    distribution_no_noise=distribution_no_noise,
                    distribution_with_noise=distribution_with_noise,
                    execution_time=execution_time
                ))
        # print("Execution complete. Results:")
        # for machine_name, results in executionresult.items():
        #     print(f"  {machine_name}:")
        #     for result in results:
        #         print(f"    Job: {result.job_info[0].job_name}")
        #         print(f"      No Noise: {result.distribution_no_noise}")
        #         print(f"      With Noise: {result.distribution_with_noise}")
        #         print(f"      Execution Time: {result.execution_time}")
        return executionresult