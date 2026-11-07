"""Workload and quantum hardware machine loader phase (Phase 1)."""

from __future__ import annotations

from typing import Any
import random

from mqt.bench import BenchmarkLevel, get_benchmark

from source.models.job import JobInfo
from source.models.machine import MachineCharacteristic
from source.models.simulation_config import SimulationConfig
from source.simulator.backends import get_fake_backend


class InputPhase:
    """Collect circuits and target machines before scheduling, driven strictly by SimulationConfig."""

    def __init__(self, config: SimulationConfig | dict[str, Any] | None = None) -> None:
        """Initialize input phase with centralized simulation configuration (SSOT)."""
        self.config = SimulationConfig.resolve(config)

    def create_input(
        self, capture_result_schedule: Any
    ) -> tuple[dict[str, JobInfo], dict[str, MachineCharacteristic]]:
        """Create the input for the scheduling phase, including both circuit jobs and quantum machines.

        Returns:
            Tuple containing:
            - Dictionary of JobInfo objects with job name as key.
            - Dictionary of MachineCharacteristic objects with machine name as key.
        """
        origin_job_info = self._create_circuit_jobs(capture_result_schedule)
        machines = self._setup_quantum_machines(capture_result_schedule)

        print("Created circuit jobs: ", end="")
        for job_name, job_info in origin_job_info.items():
            if job_info.circuit is not None:
                print(f"[{job_name}: {job_info.circuit.num_qubits} qubits] ", end="")
        print()

        print("Created quantum machines: ", end="")
        for machine_name, machine_backend in machines.items():
            print(f"[{machine_name}: {machine_backend.capacity} qubits] ", end="")
        print()

        return origin_job_info, machines

    def _create_circuit_jobs(self, capture_result_schedule: Any) -> dict[str, JobInfo]:
        """Create the list of quantum circuits driven strictly by config."""
        benchmark_name = self.config.workload.benchmark
        jobs_def = self.config.workload.jobs
        generator_def = self.config.workload.generator

        origin_job_info: dict[str, JobInfo] = {}

        if jobs_def:
            for job_name, job_spec in jobs_def.items():
                if isinstance(job_spec, (tuple, list)):
                    num_qubits = int(job_spec[0])
                    shots = int(job_spec[1]) if len(job_spec) > 1 else 1024
                    arrival_time = float(job_spec[2]) if len(job_spec) > 2 else 0.0
                    priority = int(job_spec[3]) if len(job_spec) > 3 else 1
                elif isinstance(job_spec, dict):
                    num_qubits = int(job_spec.get("qubits") or job_spec.get("num_qubits", 2))
                    shots = int(job_spec.get("shots", 1024))
                    arrival_time = float(job_spec.get("arrival_time", 0.0))
                    priority = int(job_spec.get("priority", 1))
                else:
                    num_qubits = int(job_spec)
                    shots = 1024
                    arrival_time = 0.0
                    priority = 1

                circuit = get_benchmark(benchmark_name, level=BenchmarkLevel.ALG, circuit_size=num_qubits)
                origin_job_info[job_name] = JobInfo(
                    job_name=job_name,
                    circuit=circuit,
                    num_qubits=num_qubits,
                    shots=shots,
                    arrival_time=arrival_time,
                    priority=priority,
                )
        elif generator_def:
            rng = random.Random(self.config.execution.seed)
            num_jobs = int(generator_def.get("num_jobs", 4))
            min_q = int(generator_def.get("min_qubits", 2))
            max_q = int(generator_def.get("max_qubits", 7))
            shots = int(generator_def.get("shots", 1024))

            for i in range(1, num_jobs + 1):
                job_name = f"job{i}"
                num_qubits = rng.randint(min_q, max_q)
                circuit = get_benchmark(benchmark_name, level=BenchmarkLevel.ALG, circuit_size=num_qubits)
                origin_job_info[job_name] = JobInfo(
                    job_name=job_name,
                    circuit=circuit,
                    num_qubits=num_qubits,
                    shots=shots,
                    arrival_time=0.0,
                    priority=1,
                )
        else:
            raise ValueError(
                "No circuits specified in workload configuration. "
                "Must provide 'jobs' or 'generator'."
            )

        # Capture metadata
        if hasattr(capture_result_schedule, "num_circuits"):
            capture_result_schedule.num_circuits = len(origin_job_info)
        if hasattr(capture_result_schedule, "name_circuits"):
            capture_result_schedule.name_circuits = benchmark_name
        valid_qubits = [job.circuit.num_qubits for job in origin_job_info.values() if job.circuit is not None]
        avg_q = (sum(valid_qubits) / len(valid_qubits)) if valid_qubits else 0.0
        if hasattr(capture_result_schedule, "average_qubits"):
            capture_result_schedule.average_qubits = avg_q

        return origin_job_info

    def _setup_quantum_machines(self, capture_result_schedule: Any) -> dict[str, MachineCharacteristic]:
        """Set up available quantum machines driven strictly by config."""
        machine_names = self.config.machines
        if not machine_names:
            raise ValueError("No quantum machines specified in configuration.")

        machines: dict[str, MachineCharacteristic] = {}
        for name in machine_names:
            backend_instance = get_fake_backend(name)
            char = MachineCharacteristic(
                name=backend_instance.name,
                quantum_machine=backend_instance,
                capacity=backend_instance.num_qubits,
            )
            machines[backend_instance.name] = char

        if hasattr(capture_result_schedule, "name_machines"):
            capture_result_schedule.name_machines = list(machines.keys())
        return machines
