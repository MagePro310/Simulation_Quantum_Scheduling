import sys
from typing import Dict

# Add the project root to sys.path if not already there
sys.path.append('./')
from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo

class PreSchedulePhase:

    def execute(self, origin_job_info: Dict[str, JobInfo]) -> Dict[str, SchedulerJobInfo]:
        """
        Prepares the jobs for scheduling 
        TODO: Implement circuit cutting if necessary.
        Args:
            origin_job_info: Dictionary of JobInfo objects containing the original job information.
        Returns:
            Dictionary of SchedulerJobInfo objects with job name as key, containing scheduling details.
        """
        scheduler_job: Dict[str, SchedulerJobInfo] = {}
        for job_name, job_info in origin_job_info.items():
            scheduler_job[job_name] = SchedulerJobInfo(
                job_information=job_info,
                assigned_machine=None,
                dispatch_order=None,
                depends_on= None 
            )
        return scheduler_job