"""Record what a simulation run was made from, so results can be traced and compared."""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess

from source.models.job import JobInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRACKED_PACKAGES = (
    "matplotlib",
    "mqt.bench",
    "numpy",
    "qiskit",
    "qiskit-addon-cutting",
    "qiskit-aer",
    "qiskit-ibm-runtime",
    "scipy",
)


def workload_fingerprint(
    jobs: dict[str, JobInfo],
    benchmark: str,
    machine_names: Iterable[str],
) -> str:
    """Hash the actual jobs and machines; machine order counts because it affects first fit."""
    payload = {
        "benchmark": benchmark,
        "jobs": {
            name: [job.num_qubits, job.shots, job.arrival_time, job.priority]
            for name, job in sorted(jobs.items())
        },
        "machines": list(machine_names),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def dependency_versions() -> dict[str, str]:
    """Return installed versions of the packages that affect simulation results."""
    versions = {}
    for package in TRACKED_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not installed"
    return versions


def git_commit() -> str:
    """Return the current commit, marked '-dirty' if the source tree has local changes."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        changes = git("status", "--porcelain", "--", "source", "configs", "run_batch.py", "run_simulation.py")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if changes else commit
