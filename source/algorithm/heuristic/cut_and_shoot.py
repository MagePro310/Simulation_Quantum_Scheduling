"""Cut&Shoot: circuit cutting combined with shot-wise distribution across QPUs.

Adapted from Bisicchia et al., "Cut&Shoot: Cutting & Distributing Quantum Circuits
Across Multiple NISQ Computers" (IEEE QCE 2024), following the policies of the
reference implementation (github.com/di-unipi-socc/Cut-and-Shoot):

1. Cut:   every eligible root circuit is cut, so each fragment is smaller and
          accumulates less noise (the paper's motivation for cutting).
2. Allocate: a fragment shot policy sets how many shots each fragment gets.
3. Split: each fragment's shots are spread over every machine that can hold it,
          using the fair policy (equal share per machine).
4. Merge and sew: done by the execution engine. Shards' counts and QPD results
          are concatenated, which equals the fair merge policy when shares are
          equal, then the cut parent is reconstructed.

Differences from the reference tool, since this framework schedules many jobs:
- Cutting uses SchedulingCutterHelper (equal-sized pieces up to the largest
  machine) instead of PennyLane's automatic cut finder.
- Cut&Shoot has no queue ordering of its own. Shards go to each machine's queue
  in job order (arrival time, then input order), with a job's fragments kept
  together; the engine packs them into batches as capacity allows.
- Only the fair split policy is implemented. The Hellinger and MISE policies of
  the shot-wise paper need calibration runs, which this static setting lacks.
"""

from __future__ import annotations

from typing import Callable

from source.algorithm.registry import register_algorithm
from source.flow.schedule.cutting.schedule_cutter_helper import SchedulingCutterHelper
from source.flow.schedule.shots import ShotDistributionHelper
from source.models.job import JobInfo, SchedulerJobInfo
from source.models.machine import MachineCharacteristic


def _num_qubits(info: JobInfo) -> int:
    return info.num_qubits or info.circuit.num_qubits


def _num_2q_gates(info: JobInfo) -> int:
    return sum(
        1 for instruction in info.circuit.data
        if instruction.operation.num_qubits == 2 and instruction.operation.name != "barrier"
    )


def _proportional(weights: list[float], total: int) -> list[int]:
    """Shares proportional to weights, as the reference policies do (truncated to int)."""
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [total // len(weights)] * len(weights)
    return [int(w / weight_sum * total) for w in weights]


# Fragment shot policies of the reference implementation (src/policies/*.py).
# Each maps (fragments, parent_shots) to one shot count per fragment.
FRAGMENT_SHOT_POLICIES: dict[str, Callable[[list[JobInfo], int], list[int]]] = {
    # Every fragment gets all of the parent's shots (what every other algorithm does)
    "multiplier": lambda frags, total: [total] * len(frags),
    # The parent's shots are divided equally among fragments
    "divider": lambda frags, total: [total // len(frags)] * len(frags),
    "qubit_proportional": lambda frags, total: _proportional([_num_qubits(f) for f in frags], total),
    "2qgates_proportional": lambda frags, total: _proportional([_num_2q_gates(f) for f in frags], total),
}

SPLIT_POLICIES = {"fair"}


@register_algorithm("CutAndShoot")
class CutAndShoot:
    """Cut circuits, then distribute every fragment's shots fairly across machines."""

    def __init__(
        self,
        cut_all: bool = True,
        shot_wise: bool = True,
        fragment_shot_policy: str = "multiplier",
        split_policy: str = "fair",
        **kwargs,
    ):
        """Configure the Cut&Shoot pipeline.

        Args:
            cut_all: Cut every eligible root circuit (the tool's `cutting` flag). If
                False, only circuits too large for any machine are cut, by PreSchedule.
            shot_wise: Distribute shots across machines (the tool's `shot_wise` flag).
                If False, each job runs whole on the least-loaded machine that fits it.
            fragment_shot_policy: One of FRAGMENT_SHOT_POLICIES. The default,
                "multiplier", keeps each fragment at its parent's shot count, so
                Cut&Shoot samples as much as the other algorithms.
            split_policy: Only "fair" is implemented.
        """
        if fragment_shot_policy not in FRAGMENT_SHOT_POLICIES:
            raise ValueError(
                f"Unknown fragment_shot_policy {fragment_shot_policy!r}; "
                f"choose from {sorted(FRAGMENT_SHOT_POLICIES)}."
            )
        if split_policy not in SPLIT_POLICIES:
            raise ValueError(f"Unknown split_policy {split_policy!r}; choose from {sorted(SPLIT_POLICIES)}.")
        self.cut_all = cut_all
        self.shot_wise = shot_wise
        self.fragment_shot_policy = fragment_shot_policy
        self.split_policy = split_policy

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Build the schedule; returns fragments and shards in place of the jobs they replace."""
        if not scheduler_job:
            return scheduler_job

        # 1. Cut
        jobs = self._cut(scheduler_job, machines)

        # 2. Allocate shots among each parent's fragments
        self._allocate_fragment_shots(jobs)

        # 3. Split each job's shots across the machines that fit it, and queue the pieces
        return self._split_and_assign(jobs, machines)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _cut(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        if not self.cut_all:
            return dict(scheduler_job)
        return SchedulingCutterHelper.cut_jobs(
            jobs=scheduler_job,
            target_qubits=SchedulingCutterHelper.get_max_capacity(machines),
            min_qubits=2,
        )

    def _allocate_fragment_shots(self, jobs: dict[str, SchedulerJobInfo]) -> None:
        """Set each fragment's shots from its parent's, per the fragment shot policy."""
        policy = FRAGMENT_SHOT_POLICIES[self.fragment_shot_policy]
        fragments_by_parent: dict[int, list[JobInfo]] = {}
        parents: dict[int, JobInfo] = {}
        for s_job in jobs.values():
            parent = s_job.job_information.parent_job
            if parent is not None:
                parents[id(parent)] = parent
                fragments_by_parent.setdefault(id(parent), []).append(s_job.job_information)

        for key, fragments in fragments_by_parent.items():
            total = parents[key].shots or 1024
            for fragment, shots in zip(fragments, policy(fragments, total)):
                fragment.shots = max(int(shots), 1)  # Every fragment must still be sampled

    def _split_and_assign(
        self,
        jobs: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        next_order = {name: 0 for name in machines}
        load = {name: 0.0 for name in machines}  # assigned qubit-shots, for the non-shot-wise mode
        scheduled: dict[str, SchedulerJobInfo] = {}

        for job_name in self._job_order(jobs):
            s_job = jobs[job_name]
            info = s_job.job_information
            qubits = _num_qubits(info)
            eligible = [name for name, m in machines.items() if m.capacity >= qubits]
            if not eligible:
                raise ValueError(f"Job {job_name} ({qubits} qubits) fits no machine.")

            shards_count = min(len(eligible), info.shots or 1)
            if self.shot_wise and shards_count >= 2 and ShotDistributionHelper.can_split(s_job):
                # Fair split: equal shares, the first machines take the remainder
                pieces = ShotDistributionHelper.split_shots(s_job, shards_count)
                placements = zip(pieces.items(), eligible)
            else:
                target = min(eligible, key=lambda name: load[name])
                placements = [((job_name, s_job), target)]

            for (name, piece), machine_name in placements:
                piece.assigned_machine = machine_name
                piece.dispatch_order = next_order[machine_name]
                next_order[machine_name] += 1
                load[machine_name] += qubits * (piece.job_information.shots or 0)
                scheduled[name] = piece

        return scheduled

    @staticmethod
    def _job_order(jobs: dict[str, SchedulerJobInfo]) -> list[str]:
        """FIFO by arrival time, keeping each cut parent's fragments together."""
        position = {name: index for index, name in enumerate(jobs)}

        def root_key(name: str):
            info = jobs[name].job_information
            root = info.parent_job or info
            first = min(
                position[n] for n, j in jobs.items()
                if (j.job_information.parent_job or j.job_information) is root
            )
            return (root.arrival_time or 0, first, position[name])

        return sorted(jobs, key=root_key)
