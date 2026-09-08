import sys
sys.path.append('./')

from typing import Tuple, Any, Dict
from mqt.bench import BenchmarkLevel, get_benchmark
from source.component.dataclass.job_info import JobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic
from source.component.ibm_simulator import sim_backend


class ConcreteInputPhase():
    """Collect circuits and target machines before scheduling."""
    
    def create_input(self, capture_result_schedule: Any) -> Tuple[Dict[str, JobInfo], Dict[str, Any]]:
        """
        Create the input for the scheduling phase, including both circuit jobs and quantum machines.
        
        Returns:
            Tuple containing:
            - Dictionary of JobInfo objects with job name as key.
            - Dictionary of quantum machines with machine name as key and backend instance as value.
        """
        origin_job_info = self._create_circuit_jobs(capture_result_schedule)
        machines = self._setup_quantum_machines(capture_result_schedule)
        
        # print the created jobs name: qubits
        print("Created circuit jobs: ", end="")
        for job_name, job_info in origin_job_info.items():
            if job_info.circuit is not None:
                print(f"[{job_name}: {job_info.circuit.num_qubits} qubits] ", end="")
        print()  # Xuống dòng sau khi in xong toàn bộ vòng lặp (nếu cần)
        
        # print the created machines name: qubits
        print("Created quantum machines: ", end="")
        for machine_name, machine_backend in machines.items():
            print(f"[{machine_name}: {machine_backend.capacity} qubits] ", end="")
        print()  # Xuống dòng sau khi in xong toàn bộ vòng lặp (nếu cần)
        return origin_job_info, machines

    def _create_circuit_jobs(self, capture_result_schedule: Any) -> Dict[str, JobInfo]:
        """
        Create the list of quantum circuits that need to be run.
        
        Returns:
            Dictionary of JobInfo objects with job name as key.
        """
        # Prepare benchmark jobs: simple GHZ circuits of fixed width
        jobs: Dict[str, Tuple[int, int]] = {"job1": (2, 1024), "job2": (2, 1024), "job3": (3, 1024), "job4": (2, 1024), "job5": (3, 1024), "job6": (4, 1024), "job7": (5, 1024), "job8": (2, 1024), "job9": (3, 1024), "job10": (4, 1024)}

        # Generate circuits and job infos
        origin_job_info: Dict[str, JobInfo] = {}
        for job_name, (num_qubits, shots) in jobs.items():
            origin_job_info[job_name] = JobInfo(
                job_name=job_name,
                circuit= get_benchmark("ghz", level=BenchmarkLevel.ALG, circuit_size=num_qubits),
                num_qubits=num_qubits,
                shots=shots,
                arrival_time=0,  # For simplicity, all jobs arrive at time 0
                priority=1,  # For simplicity, all jobs have the same priority
            )

        # capture
        capture_result_schedule.numCircuits = len(origin_job_info)
        capture_result_schedule.nameCircuits = "ghz"
        capture_result_schedule.averageQubits = sum([job.circuit.num_qubits for job in origin_job_info.values() if job.circuit is not None]) / len(origin_job_info)
        return origin_job_info

    def _setup_quantum_machines(self, capture_result_schedule: Any) -> Dict[str, Any]:
        """
        Set up the list of available quantum machines.
        
        Returns:
            Dictionary of quantum machines with machine name as key and backend instance as value.
        """
        machines: Dict[str, Any] = {}
        machines[sim_backend.sim_machine5qubits.FakeBelemV2().name] = MachineCharacteristic(
            name=sim_backend.sim_machine5qubits.FakeBelemV2().name,
            quantum_machine=sim_backend.sim_machine5qubits.FakeBelemV2(),
            capacity=sim_backend.sim_machine5qubits.FakeBelemV2().num_qubits
        )
        machines[sim_backend.sim_machine5qubits.FakeBogotaV2().name] = MachineCharacteristic(
            name=sim_backend.sim_machine5qubits.FakeBogotaV2().name,
            quantum_machine=sim_backend.sim_machine5qubits.FakeBogotaV2(),
            capacity=sim_backend.sim_machine5qubits.FakeBogotaV2().num_qubits
        )
        
        # capture
        capture_result_schedule.nameMachines = list(machines.keys())
        
        return machines

