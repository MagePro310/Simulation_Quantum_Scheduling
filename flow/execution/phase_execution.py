from abc import ABC, abstractmethod
from typing import Any, Dict
import sys
from copy import deepcopy

# Add the project root to sys.path if not already there
sys.path.append('./')

from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *

# Transpilation imports (merged into execution phase)
from qiskit.compiler import transpile
import mapomatic as mm


class ExecutionPhase(ABC):
    """
    Abstract base class for the Execution Phase.
    
    This merged phase performs both transpilation (when needed) and execution
    simulation. If `transpiled_job` is provided the phase will only run the
    execution simulation; otherwise it will transpile jobs first.
    """
    @abstractmethod
    def execute(
        self,
        scheduler_job_estimate: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, JobExecutionRelation] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        pass


class ConcreteExecutionPhase(ExecutionPhase):
    def _clone_scheduler_jobs(
        self,
        scheduler_job_estimate: Dict[str, SchedulerJobInfo],
    ) -> Dict[str, SchedulerJobInfo]:
        return {
            job_name: deepcopy(job_info)
            for job_name, job_info in scheduler_job_estimate.items()
        }

    def _execution_duration(
        self,
        job_name: str,
        transpiled_job: Dict[str, TranspiledJob],
        scheduler_job_simulation: Dict[str, SchedulerJobInfo],
    ) -> float:
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

    def _machine_order_from_relations(
        self,
        machine_name: str,
        execution_job_relations: Dict[str, JobExecutionRelation] | None,
        scheduler_job_simulation: Dict[str, SchedulerJobInfo],
    ) -> list[str]:
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

    def _transpile_jobs(
        self,
        scheduler_job_estimate: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, JobExecutionRelation] | None,
    ) -> Dict[str, TranspiledJob]:
        transpiled_job: Dict[str, TranspiledJob] = {}

        if execution_job_relations is not None:
            transpile_inputs = {
                job_name: relation.scheduler_job
                for job_name, relation in execution_job_relations.items()
                if relation.scheduler_job is not None
            }
        else:
            transpile_inputs = scheduler_job_estimate

        for job_name, job_info in transpile_inputs.items():
            machine_name = job_info.assigned_machine
            if execution_job_relations is not None and job_name in execution_job_relations:
                machine_name = execution_job_relations[job_name].machine_name or machine_name

            transpiled_job[job_name] = TranspiledJob(
                job_information=job_info.job_information,
                machine_name=machine_name,
            )

            try:
                transpiled_job_temp = transpile(job_info.job_information.circuit, machines[machine_name])
                layouts = mm.matching_layouts(transpiled_job_temp, machines[machine_name])
                scores = mm.evaluate_layouts(transpiled_job_temp, layouts, machines[machine_name])

                best_layout = scores[0][0]
                number_of_qubits = job_info.job_information.circuit.num_qubits
                best_layout = best_layout[0:number_of_qubits]
                transpiled_job[job_name].physical_layout = best_layout
                transpiled_job[job_name].transpiled_circuit = transpile(
                    job_info.job_information.circuit,
                    machines[machine_name],
                    initial_layout=best_layout,
                    scheduling_method='alap',
                )

            except Exception:
                # If transpilation fails, leave circuit/transpiled_circuit as None
                pass

            if execution_job_relations is not None and job_name in execution_job_relations:
                execution_job_relations[job_name].transpiled_job = transpiled_job[job_name]

        return transpiled_job

    def _build_machine_jobs_map(
        self,
        scheduler_job_simulation: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, JobExecutionRelation] | None,
    ) -> Dict[str, list[str]]:
        machine_jobs_map: Dict[str, list[str]] = {}

        if execution_job_relations:
            for machine_name in machines.keys():
                ordered = self._machine_order_from_relations(
                    machine_name,
                    execution_job_relations,
                    scheduler_job_simulation,
                )
                if ordered:
                    machine_jobs_map[machine_name] = ordered

        if not machine_jobs_map:
            for job_name, s_job in scheduler_job_simulation.items():
                machine_jobs_map.setdefault(s_job.assigned_machine, []).append(job_name)
            for machine_name in machine_jobs_map.keys():
                machine_jobs_map[machine_name].sort(
                    key=lambda job_name: scheduler_job_simulation[job_name].scheduled_start_time
                )

        return machine_jobs_map

    def _apply_execution_timing(
        self,
        scheduler_job_simulation: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        transpiled_job: Dict[str, TranspiledJob],
        execution_job_relations: Dict[str, JobExecutionRelation] | None,
    ) -> Dict[str, SchedulerJobInfo]:
        machine_jobs_map = self._build_machine_jobs_map(
            scheduler_job_simulation,
            machines,
            execution_job_relations,
        )

        machine_time_cursor: Dict[str, float] = {m: 0.0 for m in machines.keys()}

        for machine_name, ordered_jobs in machine_jobs_map.items():
            for job_name in ordered_jobs:
                if job_name not in scheduler_job_simulation:
                    continue

                sim_job = scheduler_job_simulation[job_name]
                duration = self._execution_duration(job_name, transpiled_job, scheduler_job_simulation)

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

    def execute(
        self,
        scheduler_job_estimate: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, JobExecutionRelation] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """
        Simulate execution based on transpiled circuits. If `transpiled_job` is
        None, perform transpilation first (using available execution relations
        or the schedule estimate), then run the execution simulation.
        """
        scheduler_job_simulation = self._clone_scheduler_jobs(scheduler_job_estimate)
        

        # Phase 1: Transpilation - transpile all jobs first to get actual circuit durations

        transpiled_job = self._transpile_jobs(
            scheduler_job_estimate,
            machines,
            execution_job_relations,
        )
        # Phase 2: Execution - calculate actual execution times based on transpiled circuits
        return self._apply_execution_timing(
            scheduler_job_simulation,
            machines,
            transpiled_job,
            execution_job_relations,
        )
        