import sys
sys.path.append('./')

from typing import Any, Dict
from source.component.dataclass.job_info import SchedulerJobInfo


class MainScheduleAlgorithm():
    def execute(self, algorithm: Any, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any]) -> Dict[str, SchedulerJobInfo]:
        """
        Base scheduling algorithm using FFD.

        Args:
            scheduler_job: Dictionary of jobs to be scheduled.
            machines: Dictionary of available machines.

        Returns:
            Updated scheduler_job with scheduling information.
        """
        return algorithm.execute(scheduler_job, machines)