

from typing import Any, Dict
from copy import deepcopy

from component.dataclass.machine_characteristic import *
from component.dataclass.job_info import *
from component.dataclass.result_schedule import *


class MainExecutionQuantum:
    def execute(
        self,
        scheduler_job_estimate: Dict[str, SchedulerJobInfo],
        machines: Dict[str, Any],
        transpiled_job: Dict[str, TranspiledJob],
        execution_job_relations: Dict[str, Any] | None = None,
    ) -> Dict[str, SchedulerJobInfo]:
        scheduler_job_simulation = self._clone_scheduler_jobs(scheduler_job_estimate)
        return self._apply_execution_timing(
            scheduler_job_simulation,
            machines,
            transpiled_job,
            execution_job_relations,
        )