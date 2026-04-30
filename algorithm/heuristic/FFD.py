from typing import Any, Dict
import sys

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.job_info import SchedulerJobInfo
from flow.schedule.estimated import estimated_schedule

class FFD:
    """
    First-Fit Decreasing scheduler for quantum jobs.

    Jobs are processed in descending order of circuit width. For each job,
    the scheduler scans machines in the provided order and picks the first
    machine that can host the circuit and is available at the job's arrival
    time. If no machine is available immediately, the first machine with
    enough qubits is selected and the job waits until that machine becomes
    free.
    """

    @staticmethod
    def _job_qubits(job_info: SchedulerJobInfo) -> int:
        circuit = job_info.job_information.circuit if job_info.job_information else None
        return int(getattr(circuit, 'num_qubits', 0) or 0)

    @staticmethod
    def _machine_qubits(machine: Any) -> int:
        return int(getattr(machine, 'num_qubits', 0) or 0)

    @staticmethod
    def _job_arrival_time(job_info: SchedulerJobInfo) -> float:
        if job_info.job_information is None:
            return 0.0
        arrival_time = job_info.job_information.arrival_time
        return float(arrival_time if arrival_time is not None else 0.0)

    @staticmethod
    def _machine_available_time(machine_state: Dict[str, Any]) -> float:
        return float(machine_state['available_time'])

    @staticmethod
    def _find_first_fitting_machine(
        job_info: SchedulerJobInfo,
        machine_states: list[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        required_qubits = FFD._job_qubits(job_info)
        arrival_time = FFD._job_arrival_time(job_info)

        # First try to fit at arrival_time on the first machine in order
        for machine_state in machine_states:
            if FFD._machine_qubits(machine_state['machine']) < required_qubits:
                continue
            duration = float(max(1.0, getattr(job_info.job_information.circuit, 'depth', lambda: 1)()))
            start = arrival_time
            end = start + duration
            if FFD._capacity_available(machine_state, start, end, required_qubits):
                return machine_state

        # Otherwise, find earliest slot per machine (first-fit by machine order)
        for machine_state in machine_states:
            if FFD._machine_qubits(machine_state['machine']) < required_qubits:
                continue
            earliest = FFD._earliest_start_for_machine(machine_state, arrival_time, job_info, required_qubits)
            if earliest is not None:
                machine_state.setdefault('_candidate_start', earliest)
                return machine_state

        return None

    @staticmethod
    def _capacity_available(machine_state: Dict[str, Any], start: float, end: float, required_qubits: int) -> bool:
        """Return True if the machine has enough free qubits for [start, end)."""
        capacity = FFD._machine_qubits(machine_state['machine'])
        allocations = machine_state.get('allocations', [])
        # Sum overlapping allocations
        used = 0
        for alloc in allocations:
            if alloc['start'] < end and alloc['end'] > start:
                used += alloc['qubits']
                if used + required_qubits > capacity:
                    return False
        return used + required_qubits <= capacity

    @staticmethod
    def _earliest_start_for_machine(machine_state: Dict[str, Any], arrival: float, job_info: SchedulerJobInfo, required_qubits: int) -> float | None:
        """Find earliest start >= arrival where capacity is available for job duration.

        Returns start time or None if not found (practically never None if machine has enough qubits).
        """
        allocations = machine_state.get('allocations', [])
        duration = float(max(1.0, float(estimated_schedule(job_info.job_information.circuit, shots=(job_info.job_information.shots if job_info.job_information and job_info.job_information.shots is not None else 1024)))))

        # Candidate times: arrival and all allocation end times >= arrival
        candidates = {arrival}
        for alloc in allocations:
            if alloc['end'] >= arrival:
                candidates.add(alloc['end'])

        for t in sorted(candidates):
            if FFD._capacity_available(machine_state, t, t + duration, required_qubits):
                return t

        # If no gap found, try after the latest end
        latest_end = max([alloc['end'] for alloc in allocations], default=arrival)
        if FFD._capacity_available(machine_state, latest_end, latest_end + duration, required_qubits):
            return latest_end

        return None
    
    @staticmethod
    def execute(scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any]) -> Dict[str, SchedulerJobInfo]:
        """
        Execute the FFD scheduling algorithm.
        
        Args:
            scheduler_job: Dictionary of SchedulerJobInfo objects with job name as key
            machines: Dictionary of quantum machine backends with machine name as key
            
        Returns:
            Updated scheduler_job dictionary with assigned machines and scheduled times
        """
        if not scheduler_job:
            return scheduler_job

        machine_states = [
            {
                'name': machine_name,
                'machine': machine_backend,
                'available_time': 0.0,
            }
            for machine_name, machine_backend in machines.items()
        ]

        sorted_jobs = sorted(
            scheduler_job.items(),
            key=lambda item: FFD._job_qubits(item[1]),
            reverse=True,
        )

        for job_name, job_info in sorted_jobs:
            required_qubits = FFD._job_qubits(job_info)
            machine_state = FFD._find_first_fitting_machine(job_info, machine_states)
            if machine_state is None:
                raise ValueError(
                    f"No available machine can host job '{job_name}' with {required_qubits} qubits"
                )

            circuit = job_info.job_information.circuit
            shots = (
                job_info.job_information.shots
                if job_info.job_information and job_info.job_information.shots is not None
                else 1024
            )
            arrival_time = FFD._job_arrival_time(job_info)

            # If a candidate start was computed in _find_first_fitting_machine, prefer it
            candidate_start = machine_state.pop('_candidate_start', None)
            if candidate_start is not None:
                start_time = float(candidate_start)
            else:
                # otherwise, try at arrival or the machine's latest end
                start_time = arrival_time

            execution_time = float(max(1.0, float(estimated_schedule(circuit, shots=shots))))
            end_time = start_time + execution_time

            # Record allocation on machine
            alloc = {
                'job': job_name,
                'start': start_time,
                'end': end_time,
                'qubits': required_qubits,
            }
            machine_state.setdefault('allocations', []).append(alloc)

            job_info.assigned_machine = machine_state['name']
            job_info.scheduled_start_time = start_time
            job_info.scheduled_end_time = end_time

        return scheduler_job
