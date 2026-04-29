from collections import defaultdict
from typing import Dict

from component.dataclass.job_info import SchedulerJobInfo, TranspiledJob, JobExecutionRelation


def build_job_relations(jobs):
    jobs_by_machine = defaultdict(list)
    for j in jobs:
        jobs_by_machine[j["machine"]].append(j)

    relations = []

    for m, js in jobs_by_machine.items():
        js_sorted = sorted(js, key=lambda x: (x["start"], x["end"]))

        for cur in js_sorted:
            prev_job = None
            prev_end = None
            for cand in js_sorted:
                if cand["end"] <= cur["start"]:
                    if prev_end is None or cand["end"] > prev_end:
                        prev_end = cand["end"]
                        prev_job = cand["job"]

            next_job = None
            next_start = None
            for cand in js_sorted:
                if cand["start"] >= cur["end"]:
                    if next_start is None or cand["start"] < next_start:
                        next_start = cand["start"]
                        next_job = cand["job"]

            relations.append(
                {
                    "job": cur["job"],
                    "machine": m,
                    "prev_job_on_machine": prev_job,
                    "next_job_on_machine": next_job,
                }
            )

    return relations


def build_job_relations_from_schedule(
    scheduler_job_estimate: Dict[str, SchedulerJobInfo],
    transpiled_job: Dict[str, TranspiledJob] | None = None,
) -> Dict[str, JobExecutionRelation]:
    """
    Build previous/next job links on each machine from scheduled jobs,
    and attach transpilation info into a single execution-ready dataclass.
    """
    transpiled_job = transpiled_job or {}

    jobs = []
    for job_name, job_info in scheduler_job_estimate.items():
        jobs.append(
            {
                "job": job_name,
                "machine": job_info.assigned_machine,
                "start": job_info.scheduled_start_time,
                "end": job_info.scheduled_end_time,
            }
        )

    raw_relations = build_job_relations(jobs)

    relations_by_job: Dict[str, JobExecutionRelation] = {}
    for rel in raw_relations:
        job_name = rel["job"]
        if job_name not in scheduler_job_estimate:
            continue

        relations_by_job[job_name] = JobExecutionRelation(
            job_name=job_name,
            machine_name=rel["machine"],
            scheduler_job=scheduler_job_estimate[job_name],
            transpiled_job=transpiled_job.get(job_name),
            prev_job_on_machine=rel["prev_job_on_machine"],
            next_job_on_machine=rel["next_job_on_machine"],
        )

    return relations_by_job
