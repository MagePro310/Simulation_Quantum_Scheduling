import sys
sys.path.append('./')
from typing import Any, Dict

from flow.execution.main_execution_quantum import MainExecutionQuantum
from flow.execution.post_execution_analysis import PostExecution
from flow.execution.pre_execution_transpile import PreExecution

from component.dataclass.job_info import ExecutionResult, JobInfo


class ConcreteExecutionPhase:
    def __init__(self):
        self.pre_phase = PreExecution()
        self.main_execution = MainExecutionQuantum()
        self.post_execution = PostExecution()

    def execute(
        self,
        machines: Dict[str, Any],
        execution_job_relations: Dict[str, JobInfo],
    ) -> Dict[str, ExecutionResult]:
        """Delegate transpilation and execution to dedicated classes."""
        transpiled_job = self.pre_phase.transpile_jobs(
            machines,
            execution_job_relations,
        )

        execution_result = self.main_execution.execute(
            machines=machines,
            transpiled_job=transpiled_job,
        )

        # Analyze the results and update the job info with execution results.
        analyzed_results = self.post_execution.execute(
            machines=machines,
            scheduler_job_simulation=execution_result,
        )

        return analyzed_results
