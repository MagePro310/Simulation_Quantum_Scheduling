import sys
from typing import Any, Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.flow.schedule.circuit_cutter import CircuitCutter


class PreSchedulePhase:
    """Prepares the jobs for scheduling, cutting circuits that exceed machine capacities."""

    def __init__(self, cutting_policy: str = "greedy"):
        self.cutting_policy = cutting_policy.lower()
        self.circuit_cutter = CircuitCutter()

    def execute(
        self,
        origin_job_info: Dict[str, JobInfo],
        machines: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Prepares jobs for scheduling and applies circuit cutting if necessary.

        Args:
            origin_job_info: Dictionary of original JobInfo objects.
            machines: Dictionary of available MachineCharacteristic instances.

        Returns:
            Dictionary of SchedulerJobInfo objects ready for scheduling.
        """
        scheduler_job: Dict[str, SchedulerJobInfo] = {}

        max_capacity = None
        if machines:
            max_capacity = max(
                (getattr(m, "capacity", 0) for m in machines.values()),
                default=None,
            )

        policy_name = "half" if self.cutting_policy == "half" else "greedy"

        for job_name, job_info in origin_job_info.items():
            num_qubits = job_info.num_qubits
            if num_qubits is None and job_info.circuit is not None:
                num_qubits = job_info.circuit.num_qubits

            # Check if circuit exceeds machine capacity and requires cutting
            if max_capacity is not None and num_qubits is not None and num_qubits > max_capacity:
                print(
                    f"Applying {policy_name} circuit cutting: {job_name} ({num_qubits} qubits > "
                    f"machine capacity {max_capacity} qubits)..."
                )
                children_jobs = self.circuit_cutter.cut_circuit(job_info, max_capacity, policy=policy_name)
                sub_qubit_sizes = [c.num_qubits for c in children_jobs.values()]
                print(
                    f"  -> Cut {job_name} into {len(children_jobs)} subcircuits: "
                    f"{sub_qubit_sizes} qubits (overhead: {job_info.cutting_overhead:g})"
                )

                for child_name, child_job in children_jobs.items():
                    scheduler_job[child_name] = SchedulerJobInfo(
                        job_information=child_job,
                        assigned_machine=None,
                        dispatch_order=None,
                        depends_on=None,
                    )
            else:
                scheduler_job[job_name] = SchedulerJobInfo(
                    job_information=job_info,
                    assigned_machine=None,
                    dispatch_order=None,
                    depends_on=None,
                )

        return scheduler_job