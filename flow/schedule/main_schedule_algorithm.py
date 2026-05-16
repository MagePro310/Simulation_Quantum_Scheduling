from abc import ABC, abstractmethod
import sched
from typing import Any, Dict, Tuple
import time
import sys
from copy import deepcopy

from algorithm.heuristic.FFD import FFD
from component.dataclass.job_info import SchedulerJobInfo


class MainScheduleAlgorithm():
    def base_schedule_algorithm(self, scheduler_job: Dict[str, SchedulerJobInfo], machines: Dict[str, Any]) -> Dict[str, SchedulerJobInfo]:
        """
        Base scheduling algorithm using FFD.

        Args:
            scheduler_job: Dictionary of jobs to be scheduled.
            machines: Dictionary of available machines.

        Returns:
            Updated scheduler_job with scheduling information.
        """
        print("Scheduling jobs on machines using FFD algorithm...")
        return FFD.execute(scheduler_job, machines)