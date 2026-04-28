from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Dict, Type
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from mqt.bench import BenchmarkLevel, get_benchmark
from component.dataclass.job_info import JobInfo
from component.ibm_simulator import sim_backend

class BaseInputPhase(ABC):
    """
    Abstract base class for the Input Phase.
    
    Input: (quantum circuit, priority) and set quantum machine
    Output: (set quantum circuit, priority) and set quantum machine
    """
       
    @abstractmethod
    def create_input(self, capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo], Dict[str, Any]]:
        """
        Create the input for the scheduling phase, including both circuit jobs and quantum machines.
        
        Returns:
            Tuple containing:
            - Dictionary of JobInfo objects with job name as key.
            - Dictionary of quantum machines with machine name as key and backend instance as value.
        """
        pass


class ConcreteInputPhase(BaseInputPhase):
    """Collect circuits and target machines before scheduling."""
    
    def create_input(self, capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo], Dict[str, Any]]:
        """
        Create the input for the scheduling phase, including both circuit jobs and quantum machines.
        
        Returns:
            Tuple containing:
            - Dictionary of JobInfo objects with job name as key.
            - Dictionary of quantum machines with machine name as key and backend instance as value.
        """
        origin_job_info = self.create_circuit_jobs(capture_result_schedule)
        machines = self.setup_quantum_machines(capture_result_schedule)
        return origin_job_info, machines

    def create_circuit_jobs(self, capture_result_schedule: Any) -> Dict[str, JobInfo]:
        """
        Create the list of quantum circuits that need to be run.
        
        Returns:
            Dictionary of JobInfo objects with job name as key.
        """
        # Prepare benchmark jobs: simple GHZ circuits of fixed width
        jobs: Dict[str, Tuple[int, int]] = {"job1": (2, 1024), "job2": (2, 1024), "job3": (3, 1024), "job4": (2, 1024)}

        # Generate circuits and job infos
        origin_job_info: Dict[str, JobInfo] = {}
        for job_name, (num_qubits, shots) in jobs.items():
            origin_job_info[job_name] = JobInfo(
                job_name=job_name,
                circuit= get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=num_qubits),
                shots=shots,
                arrival_time=0,  # For simplicity, all jobs arrive at time 0
                priority=1,  # For simplicity, all jobs have the same priority
            )

        # capture
        capture_result_schedule.numCircuits = len(origin_job_info)
        capture_result_schedule.nameCircuits = "ghz"
        capture_result_schedule.averageQubits = sum([job.circuit.num_qubits for job in origin_job_info.values()]) / len(origin_job_info)


        return origin_job_info

    def setup_quantum_machines(self, capture_result_schedule: Any) -> Dict[str, Any]:
        """
        Set up the list of available quantum machines.
        
        Returns:
            Dictionary of quantum machines with machine name as key and backend instance as value.
        """
        machines: Dict[str, Any] = {}
        machines[sim_backend.sim_machine5qubits.FakeBelemV2().name] = sim_backend.sim_machine5qubits.FakeBelemV2()
        machines[sim_backend.sim_machine5qubits.FakeBogotaV2().name] = sim_backend.sim_machine5qubits.FakeBogotaV2()
        
        # capture
        capture_result_schedule.nameMachines = list(machines.keys())
        
        return machines

