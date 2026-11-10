"""Execution time estimation utilities for quantum circuits and jobs."""

from __future__ import annotations

from typing import Any


def estimate_job_duration(job: Any) -> float:
    """Estimate circuit execution duration based on circuit depth and shots.

    Args:
        job: JobInfo or SchedulerJobInfo instance.

    Returns:
        float: Estimated execution duration in seconds.
    """
    if job is None:
        return 0.0

    info = getattr(job, "job_information", job)
    if info is None or getattr(info, "circuit", None) is None:
        return 0.0

    shots = getattr(info, "shots", 1024) or 1024
    depth = getattr(info.circuit, "depth", lambda: 1)()
    return float(max(depth, 1) * shots)


def shots_duration(duration_per_shot: float, shots: int, rep_delay: float) -> float:
    """Wall time, in seconds, to run a circuit for `shots` shots on a device.

    Each shot is the circuit itself (gates and measurement, from the transpiled
    schedule) followed by the device's rep_delay before the next shot starts.
    """
    return float(shots) * (float(duration_per_shot) + float(rep_delay))
