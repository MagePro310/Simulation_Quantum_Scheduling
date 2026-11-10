"""Execution time estimation utilities for quantum circuits and jobs."""

from __future__ import annotations

from typing import Any


def num_circuit_runs(job: Any) -> int:
    """Number of distinct circuits the engine runs for a job, each for the job's full shots.

    A cut subcircuit runs every one of its QPD subexperiments (6 per cut CNOT, 6^k for
    k cuts); any other job runs one circuit.
    """
    info = getattr(job, "job_information", job)
    subexperiments = getattr(info, "subexperiments", None)
    return len(subexperiments) if subexperiments else 1


def estimate_job_duration(job: Any) -> float:
    """Relative duration estimate used by schedulers: depth x shots x circuit runs.

    This is a unitless proxy, not seconds, computed on the untranspiled circuit. It
    leaves out gate times and rep_delay by design: schedulers decide from
    pre-compilation information only. The engine's actual batch time comes from
    shots_duration on the transpiled circuit.
    The circuit-run factor matters for cut subcircuits, which run every subexperiment
    for the full shot count; without it a fragment looks 6^k times shorter than it is.

    Args:
        job: JobInfo or SchedulerJobInfo instance.

    Returns:
        float: Relative duration (0.0 for a job without a circuit).
    """
    if job is None:
        return 0.0

    info = getattr(job, "job_information", job)
    if info is None or getattr(info, "circuit", None) is None:
        return 0.0

    shots = getattr(info, "shots", 1024) or 1024
    depth = getattr(info.circuit, "depth", lambda: 1)()
    return float(max(depth, 1) * shots * num_circuit_runs(info))


def shots_duration(duration_per_shot: float, shots: int, rep_delay: float) -> float:
    """Wall time, in seconds, to run a circuit for `shots` shots on a device.

    Each shot is the circuit itself (gates and measurement, from the transpiled
    schedule) followed by the device's rep_delay before the next shot starts.
    """
    return float(shots) * (float(duration_per_shot) + float(rep_delay))
