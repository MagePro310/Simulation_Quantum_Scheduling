from typing import Any, Dict

from flow.execution.main_execution_quantum import MainExecutionQuantum
from flow.execution.post_execution_analysis import PostExecution
from flow.execution.pre_execution_transpile import PreExecution

from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *


class ConcreteExecutionPhase:
    def __init__(self):
        self.pre_phase = PreExecution()
        # self.main_execution = MainExecutionQuantum()
        # self.post_execution = PostExecution()

    def execute(
        self,
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        """Delegate transpilation and execution to dedicated classes."""
        transpiled_job = self.pre_phase.transpile_jobs(
            machines,
            execution_job_relations,
        )
        # scheduler_job_execution = self.main_execution.execute(
        #     machines=machines,
        #     transpiled_job=transpiled_job,
        # )