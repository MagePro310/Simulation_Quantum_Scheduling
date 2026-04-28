
from abc import ABC, abstractmethod
from typing import Any, Dict
import sys
import time
from copy import deepcopy

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *


class ExecutionPhase(ABC):
    """
    Abstract base class for the Execution Phase.
    
    Input: Output of transpile phase (transpiled circuits)
    Output: Execution results from running circuits on quantum machines
    """
    @abstractmethod
    def execute(self, scheduler_job_estimate: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], 
                transpiled_job: Dict[str, TranspiledJob],
                execution_job_relations: Dict[str, JobExecutionRelation] | None = None) -> Dict[str, SchedulerJobInfo]:
        pass


class ConcreteExecutionPhase(ExecutionPhase):
    def execute(self, scheduler_job_estimate: Dict[str, SchedulerJobInfo], machines: Dict[str, Any], 
                                transpiled_job: Dict[str, TranspiledJob],
                                execution_job_relations: Dict[str, JobExecutionRelation] | None = None) -> Dict[str, SchedulerJobInfo]:
        """
        Simulate execution based on transpiled circuits.

        The method recomputes start/end times from transpiled workload cost while
        preserving the machine-local execution order. If relation data is provided,
        precedence is taken from `prev_job_on_machine` / `next_job_on_machine`.
        """
        scheduler_job_simulation: Dict[str, SchedulerJobInfo] = {
            job_name: deepcopy(job_info)
            for job_name, job_info in scheduler_job_estimate.items()
        }

        def _execution_duration(job_name: str) -> float:
            job_t = transpiled_job.get(job_name)
            shots = 1
            if job_t is not None and job_t.job_information is not None and job_t.job_information.shots is not None:
                shots = max(1, int(job_t.job_information.shots))
            elif scheduler_job_simulation[job_name].job_information is not None and scheduler_job_simulation[job_name].job_information.shots is not None:
                shots = max(1, int(scheduler_job_simulation[job_name].job_information.shots))

            if job_t is None or job_t.transpiled_circuit is None:
                return max(
                    1.0,
                    float(
                        scheduler_job_simulation[job_name].scheduled_end_time
                        - scheduler_job_simulation[job_name].scheduled_start_time
                    ) * shots,
                )

            circuit = job_t.transpiled_circuit
            circuit_duration = getattr(circuit, "duration", None)

            # Prefer actual transpiled duration if available.
            if circuit_duration is not None:
                return max(1.0, float(circuit_duration) * shots)

            # Fallback when duration metadata is unavailable.
            return max(
                1.0,
                float(
                    scheduler_job_simulation[job_name].scheduled_end_time
                    - scheduler_job_simulation[job_name].scheduled_start_time
                ) * shots,
            )

        def _machine_order_from_relations(machine_name: str) -> list[str]:
            if not execution_job_relations:
                return []

            machine_jobs = [
                relation for relation in execution_job_relations.values()
                if relation.machine_name == machine_name
            ]
            if not machine_jobs:
                return []

            relation_by_job = {r.job_name: r for r in machine_jobs}
            ordered: list[str] = []
            visited: set[str] = set()

            roots = sorted(
                [
                    r.job_name for r in machine_jobs
                    if r.prev_job_on_machine is None
                    or r.prev_job_on_machine not in relation_by_job
                ],
                key=lambda job_name: scheduler_job_simulation[job_name].scheduled_start_time,
            )

            def _walk(start_job: str) -> None:
                cur = start_job
                while cur is not None and cur not in visited and cur in relation_by_job:
                    visited.add(cur)
                    ordered.append(cur)
                    nxt = relation_by_job[cur].next_job_on_machine
                    if nxt in visited:
                        break
                    cur = nxt

            for root in roots:
                _walk(root)

            for leftover in sorted(
                relation_by_job.keys(),
                key=lambda job_name: scheduler_job_simulation[job_name].scheduled_start_time,
            ):
                if leftover not in visited:
                    _walk(leftover)

            return ordered

        machine_jobs_map: Dict[str, list[str]] = {}

        if execution_job_relations:
            for machine_name in machines.keys():
                ordered = _machine_order_from_relations(machine_name)
                if ordered:
                    machine_jobs_map[machine_name] = ordered

        if not machine_jobs_map:
            for job_name, s_job in scheduler_job_simulation.items():
                machine_jobs_map.setdefault(s_job.assigned_machine, []).append(job_name)
            for machine_name in machine_jobs_map.keys():
                machine_jobs_map[machine_name].sort(
                    key=lambda job_name: scheduler_job_simulation[job_name].scheduled_start_time
                )

        machine_time_cursor: Dict[str, float] = {m: 0.0 for m in machines.keys()}

        for machine_name, ordered_jobs in machine_jobs_map.items():
            for job_name in ordered_jobs:
                if job_name not in scheduler_job_simulation:
                    continue

                sim_job = scheduler_job_simulation[job_name]
                duration = _execution_duration(job_name)

                start_time = max(
                    float(sim_job.scheduled_start_time),
                    machine_time_cursor.get(machine_name, 0.0),
                )
                end_time = start_time + duration

                sim_job.assigned_machine = machine_name
                sim_job.scheduled_start_time = start_time
                sim_job.scheduled_end_time = end_time

                machine_time_cursor[machine_name] = end_time

        return scheduler_job_simulation
        