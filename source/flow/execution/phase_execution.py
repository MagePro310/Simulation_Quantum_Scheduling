import sys
sys.path.append('./')
from typing import Any, Dict

from source.component.dataclass.job_info import SchedulerJobInfo, ExecutionResult


class ConcreteExecutionPhase:
    def execute(
        self,
        machines: Dict[str, Any],
        scheduler_job: Dict[str, SchedulerJobInfo],
        capture_result_schedule: Any = None
    ) -> Dict[str, ExecutionResult]:
        """Delegate transpilation and execution to dedicated classes."""
        # from schedule result, dispatch the job to the machine
        # if have two job run parallel, merge the circuit and transpile it
        # when execution, check finished the shots required for each job
        # if execution result is not enough, run the job again until reach the shots required
        # if execution result is enough, dispatch the next job in the schedule
        