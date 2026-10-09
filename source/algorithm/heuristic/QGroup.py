"""QGroup quantum scheduling algorithm (Algorithms 1-4, Orenstein & Chaudhary, QCE 2024).

Self-contained implementation with partition-based grouping, MILP optimization,
and multi-machine assignment integrated into the quantum scheduling framework.

Reference: QGroup: Parallel Quantum Job Scheduling Using Dynamic Programming
"""

from __future__ import annotations
from dataclasses import dataclass
from math import ceil, exp, floor, gcd, isfinite, log
from functools import reduce
from typing import Callable, Hashable, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


# ============================================================================
# QGroup Core Data Structures
# ============================================================================

def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class QGroupJob:
    """Job representation for QGroup algorithms."""
    id: str
    qubits: int
    shots: int

    def __post_init__(self):
        _positive_int(self.qubits, "qubits")
        _positive_int(self.shots, "shots")
        if not self.id:
            raise ValueError("job id must not be empty")


@dataclass(frozen=True)
class QGroupMachine:
    """Machine representation for QGroup algorithms."""
    id: str
    qubits: int
    type_key: Hashable
    available_at: float = 0.0

    def __post_init__(self):
        _positive_int(self.qubits, "qubits")
        hash(self.type_key)
        if not self.id or not isfinite(self.available_at) or self.available_at < 0:
            raise ValueError("invalid machine id or available_at")


@dataclass(frozen=True)
class QGroupParameters:
    """Parameters for QGroup algorithms."""
    alpha: float = 0.25
    delta: int = 1
    eta: float = 0.75
    runtime_scale: float = 0.748
    overhead: float = 1.8
    fidelity_weight: float = 1.0
    horizon: str = "safe"  # 'safe' or 'paper'
    time_limit: float | None = None
    max_variables: int = 2_000_000

    def __post_init__(self):
        _positive_int(self.delta, "delta")
        _positive_int(self.max_variables, "max_variables")
        if not isfinite(self.eta) or not 0 < self.eta <= 1:
            raise ValueError("eta must be in (0, 1]")
        for name in ("alpha", "overhead", "fidelity_weight"):
            if not isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not isfinite(self.runtime_scale) or self.runtime_scale <= 0:
            raise ValueError("runtime_scale must be positive and finite")
        if self.horizon not in ("safe", "paper"):
            raise ValueError("horizon must be 'safe' or 'paper'")
        if self.time_limit is not None and (
            not isfinite(self.time_limit) or self.time_limit <= 0
        ):
            raise ValueError("time_limit must be positive and finite")


@dataclass
class QGroupSchedule:
    """Schedule result from QGroup algorithms."""
    jobs: tuple[QGroupJob, ...]
    delta: int
    bins: tuple[int, ...]
    X: np.ndarray
    W: np.ndarray
    C: np.ndarray  # 1 iff workload unchanged from preceding bin
    D: np.ndarray  # 1 iff bin is empty
    duration: float
    optimal: bool
    status: str

    @property
    def extra_shots(self):
        return {j.id: b * self.delta - j.shots for j, b in zip(self.jobs, self.bins)}


@dataclass
class QGroupAssignment:
    """Assignment of a schedule to a machine."""
    machine: QGroupMachine
    schedule: QGroupSchedule
    start: float
    finish: float


@dataclass
class QGroupPlan:
    """Complete scheduling plan across all machines."""
    assignments: dict[str, list[QGroupAssignment]]

    @property
    def makespan(self):
        return max((a.finish for rows in self.assignments.values() for a in rows), default=0.0)


# Type aliases for callbacks
RuntimeCallback = Callable[[QGroupJob, QGroupMachine], float]
FidelityCallback = Callable[[QGroupJob, QGroupMachine, QGroupSchedule], float]


# ============================================================================
# Algorithm 1: Partition (Dynamic Programming)
# ============================================================================

def dissimilarity(values: Sequence[float], total_jobs: int, machines: int) -> float:
    """Compute dissimilarity cost for a group of jobs (Equations 4-5)."""
    _positive_int(total_jobs, "total_jobs")
    _positive_int(machines, "machines")
    if not values or any(not isfinite(t) or t <= 0 for t in values):
        raise ValueError("runtimes must be positive and finite")
    c = min(machines, total_jobs)
    lo, hi = total_jobs // c, ceil(total_jobs / c)
    difference = max(lo - len(values), len(values) - hi) / lo
    z = exp(-difference)
    return max(values) / min(values) - 1 - z / (1 + z)


def partition(
    jobs: Sequence[QGroupJob],
    runtimes: Sequence[float],
    alpha: float = 0.25,
    machines: int = 1,
    total_jobs: int | None = None,
    cost: Callable[[Sequence[float]], float] | None = None
) -> list[tuple[QGroupJob, ...]]:
    """Algorithm 1: Interval DP for job partitioning, O(N^3) time and O(N^2) memory."""
    if len(jobs) != len(runtimes):
        raise ValueError("jobs and runtimes have different lengths")
    if len({j.id for j in jobs}) != len(jobs):
        raise ValueError("duplicate job ids")
    if not isfinite(alpha) or alpha < 0:
        raise ValueError("alpha must be nonnegative and finite")
    if any(not isfinite(t) or t <= 0 for t in runtimes):
        raise ValueError("runtimes must be positive and finite")
    n = len(jobs)
    if not n:
        return []

    order = sorted(range(n), key=lambda i: runtimes[i])
    ordered = tuple(jobs[i] for i in order)
    times = [runtimes[i] for i in order]

    if cost is None:
        total = n if total_jobs is None else total_jobs
        cost = lambda ts: dissimilarity(ts, total, machines)

    dp = np.full((n, n + 1), np.inf)
    cut = np.zeros((n, n + 1), dtype=int)
    dp[:, 1] = alpha

    for length in range(2, n + 1):
        for start in range(n - length + 1):
            dp[start, length] = cost(times[start:start + length])
            if not isfinite(dp[start, length]):
                raise ValueError("dissimilarity must be finite")
            for k in range(1, length):
                candidate = dp[start, k] + dp[start + k, length - k]
                if candidate < dp[start, length]:
                    dp[start, length], cut[start, length] = candidate, k

    # Iterative reconstruction
    groups, stack = [], [(0, n)]
    while stack:
        start, length = stack.pop()
        k = int(cut[start, length])
        if k == 0:
            groups.append(ordered[start:start + length])
        else:
            stack.extend([(start + k, length - k), (start, k)])

    return groups


# ============================================================================
# Algorithm 2: Schedule (MILP Optimization)
# ============================================================================

def compute_bins(Q: int, shots: Sequence[int], qubits: Sequence[int], delta: int = 1, eta: float = 1.0):
    """Helper to compute bins and capacity."""
    _positive_int(Q, "Q")
    _positive_int(delta, "delta")
    if not isfinite(eta) or not 0 < eta <= 1:
        raise ValueError("eta must be in (0,1]")
    if len(shots) != len(qubits):
        raise ValueError("shots and qubits have different lengths")
    for s, q in zip(shots, qubits):
        _positive_int(s, "shots")
        _positive_int(q, "qubits")

    capacity = floor(eta * Q)
    if any(q > capacity for q in qubits):
        raise ValueError("a job exceeds floor(eta * Q)")
    if not shots:
        return delta, (), 0, capacity

    delta = max(delta, reduce(gcd, shots))
    bins = tuple((s + delta - 1) // delta for s in shots)
    estimate = ceil(sum(qubits) / (eta * Q)) * max(bins)
    return delta, bins, estimate, capacity


def _result(jobs, delta, bins, X, times, p, optimal, status):
    """Create a Schedule result from MILP solution."""
    X = np.asarray(X, dtype=np.int8)
    X = X[:, X.any(axis=0)]
    previous = np.pad(X[:, :-1], ((0, 0), (1, 0))) if X.shape[1] else X.copy()
    W = ((X == 1) & (previous == 0)).astype(np.int8)
    C = np.all(X == previous, axis=0).astype(np.int8)
    D = (~X.any(axis=0)).astype(np.int8)
    duration = (p.runtime_scale * float(np.mean(times)) * delta * int((1-D).sum())
                + p.overhead * int((1-C).sum())) if jobs else 0.0
    return QGroupSchedule(tuple(jobs), delta, bins, X, W, C, D, duration, optimal, status)


def _inputs(Q, jobs, runtimes, p):
    """Validate inputs and compute bins."""
    if len(jobs) != len(runtimes) or len({j.id for j in jobs}) != len(jobs):
        raise ValueError("length mismatch or duplicate job ids")
    if any(not isfinite(t) or t <= 0 for t in runtimes):
        raise ValueError("runtimes must be positive and finite")
    return compute_bins(Q, [j.shots for j in jobs], [j.qubits for j in jobs], p.delta, p.eta)


def fast_schedule(
    Q: int,
    jobs: Sequence[QGroupJob],
    runtimes: Sequence[float],
    p: QGroupParameters = QGroupParameters()
) -> QGroupSchedule:
    """Algorithm 2 FastSchedule: first-fit greedy placement."""
    delta, bins, _, capacity = _inputs(Q, jobs, runtimes, p)
    horizon = sum(bins)
    if len(jobs) * horizon > p.max_variables:
        raise ValueError("greedy matrix too large; increase delta or max_variables")

    X = np.zeros((len(jobs), horizon), dtype=np.int8)
    load = np.zeros(horizon, dtype=int)

    for i, (job, b) in enumerate(zip(jobs, bins)):
        for start in range(horizon - b + 1):
            if np.all(load[start:start+b] + job.qubits <= capacity):
                X[i, start:start+b] = 1
                load[start:start+b] += job.qubits
                break
        else:
            raise RuntimeError("internal error: serial horizon must be feasible")

    return _result(jobs, delta, bins, X, runtimes, p, False, "greedy")


def _solve(jobs, times, p, delta, bins, capacity, B):
    """Solve MILP for optimal schedule."""
    n = len(jobs)
    offsets, count = [], 0
    for b in bins:
        offsets.append(count)
        count += B - b + 1
    x0, a0, c0 = count, count + n * B, count + n * B + B
    size = c0 + B

    if size > p.max_variables:
        raise ValueError(f"MILP needs {size} variables; increase delta or max_variables")

    rows, cols, data, lower, upper = [], [], [], [], []

    def constraint(terms, lo=-np.inf, hi=np.inf):
        r = len(lower)
        for col, val in terms:
            rows.append(r)
            cols.append(col)
            data.append(val)
        lower.append(lo)
        upper.append(hi)

    def x(i, t):
        return x0 + i * B + t

    for i, b in enumerate(bins):
        constraint([(offsets[i] + s, 1) for s in range(B-b+1)], 1, 1)
        for t in range(B):
            terms = [(x(i, t), 1)] + [(offsets[i]+s, -1)
                     for s in range(max(0, t-b+1), min(t, B-b)+1)]
            constraint(terms, 0, 0)

    for t in range(B):
        constraint([(x(i, t), job.qubits) for i, job in enumerate(jobs)], hi=capacity)
        constraint([(a0+t, 1)] + [(x(i,t), -1) for i in range(n)], hi=0)
        for i in range(n):
            constraint([(x(i,t), 1), (a0+t, -1)], hi=0)
            prev = [(x(i,t-1), -1)] if t else []
            constraint([(x(i,t), 1), (c0+t, -1), (a0+t, 1)] + prev, hi=1)
            prev = [(x(i,t-1), 1)] if t else []
            constraint([(x(i,t), -1), (c0+t, -1), (a0+t, 1)] + prev, hi=1)
        if t:
            constraint([(a0+t, 1), (a0+t-1, -1)], hi=0)

    objective = np.zeros(size)
    objective[a0:c0] = p.runtime_scale * float(np.mean(times)) * delta
    objective[c0:] = p.overhead
    matrix = coo_matrix((data, (rows, cols)), shape=(len(lower), size)).tocsc()

    options = {"mip_rel_gap": 0.0}
    if p.time_limit is not None:
        options["time_limit"] = p.time_limit

    fit = milp(objective, integrality=np.ones(size), bounds=Bounds(0, 1),
               constraints=LinearConstraint(matrix, lower, upper), options=options)

    if fit.status == 2:
        return None
    if fit.status != 0 or fit.x is None:
        raise RuntimeError(f"MILP did not prove optimality: {fit.message}")

    X = np.rint(fit.x[x0:a0]).astype(np.int8).reshape(n, B)
    return _result(jobs, delta, bins, X, times, p, True,
                   "optimal" if p.horizon == "safe" else "optimal within heuristic horizon")


def schedule(
    Q: int,
    jobs: Sequence[QGroupJob],
    runtimes: Sequence[float],
    p: QGroupParameters = QGroupParameters()
) -> QGroupSchedule:
    """Algorithm 2 Schedule: exact MILP optimization."""
    delta, bins, estimate, capacity = _inputs(Q, jobs, runtimes, p)
    if not jobs:
        return _result(jobs, delta, bins, np.zeros((0, 0)), runtimes, p, True, "empty")

    greedy = fast_schedule(Q, jobs, runtimes, p)
    B = sum(bins) if p.horizon == "safe" else min(estimate, greedy.X.shape[1])

    while True:
        result = _solve(jobs, runtimes, p, delta, bins, capacity, B)
        if result is not None:
            return result
        if B >= sum(bins):
            raise RuntimeError("MILP infeasible despite a feasible serial schedule")
        B = max(B + 1, greedy.X.shape[1])


# ============================================================================
# Algorithm 3: Assign (Greedy Machine Selection)
# ============================================================================

def assign(
    machine_types: Sequence[Sequence[QGroupMachine]],
    queue: Sequence[QGroupJob],
    runtime: RuntimeCallback,
    fidelity: FidelityCallback,
    p: QGroupParameters = QGroupParameters(),
    compress: bool = True
) -> QGroupPlan:
    """Algorithm 3: Queue-priority greedy machine selection with compression."""
    machines = [m for kind in machine_types for m in kind]
    if any(not kind for kind in machine_types):
        raise ValueError("empty machine type")
    if len({m.id for m in machines}) != len(machines):
        raise ValueError("duplicate machine ids")
    if len({j.id for j in queue}) != len(queue):
        raise ValueError("duplicate job ids")
    if queue and not machines:
        raise ValueError("no machines")

    times = {}
    for k, kind in enumerate(machine_types):
        if any(m.qubits != kind[0].qubits for m in kind):
            raise ValueError("machines in a type must have equal qubit counts")
        for j in queue:
            values = [runtime(j, m) for m in kind]
            if any(not isfinite(t) or t <= 0 for t in values):
                raise ValueError("runtime callback must return positive finite seconds")
            if any(t != values[0] for t in values):
                raise ValueError("type_key groups machines with different runtimes")
            times[k, j.id] = values[0]

    eligible = {k: [j for j in queue if j.qubits <= floor(p.eta * kind[0].qubits)]
                for k, kind in enumerate(machine_types)}
    if any(not any(j in group for group in eligible.values()) for j in queue):
        raise ValueError("at least one job cannot fit any machine under eta")

    result = {m.id: [] for m in machines}
    available = {m.id: m.available_at for m in machines}
    remaining = {j.id for j in queue}
    groups, schedules = {}, {}

    def rebuild(k):
        jobs = [j for j in eligible[k] if j.id in remaining]
        groups[k] = partition(jobs, [times[k,j.id] for j in jobs], p.alpha,
                              len(machines), total_jobs=max(1, len(remaining)))
        schedules[k] = {tuple(j.id for j in g): schedule(machine_types[k][0].qubits, g,
                          [times[k,j.id] for j in g], p) for g in groups[k]}

    for k in range(len(machine_types)):
        rebuild(k)

    for job in queue:
        if job.id not in remaining:
            continue
        candidates = []
        for k, kind in enumerate(machine_types):
            group = next((g for g in groups[k] if job in g), None)
            if group is None:
                continue
            sched = schedules[k][tuple(j.id for j in group)]
            for machine in kind:
                probabilities = [fidelity(j, machine, sched) for j in group]
                if any(not isfinite(v) or not 0 < v <= 1 for v in probabilities):
                    raise ValueError("fidelity callback must return EPST in (0,1]")
                finish = available[machine.id] + sched.duration
                score = finish - p.fidelity_weight * log(min(probabilities))
                candidates.append((score, k, machine, group, sched))

        _, chosen, machine, group, sched = min(candidates, key=lambda c: c[0])
        start = available[machine.id]
        result[machine.id].append(QGroupAssignment(machine, sched, start, start+sched.duration))
        available[machine.id] += sched.duration
        remaining.difference_update(j.id for j in group)
        groups[chosen].remove(group)

        for k in range(len(machine_types)):
            if k != chosen:
                rebuild(k)

    if compress:
        for k, kind in enumerate(machine_types):
            for machine in kind:
                if len(result[machine.id]) <= 1:
                    continue
                jobs = [j for a in result[machine.id] for j in a.schedule.jobs]
                regrouped = partition(jobs, [times[k,j.id] for j in jobs], p.alpha, 1)
                replacements, start = [], machine.available_at
                for group in regrouped:
                    sched = schedule(machine.qubits, group, [times[k,j.id] for j in group], p)
                    replacements.append(QGroupAssignment(machine, sched, start, start+sched.duration))
                    start += sched.duration
                result[machine.id] = replacements

    return QGroupPlan(result)


# ============================================================================
# Algorithm 4: QGroup (Main Entry Point)
# ============================================================================

def qgroup(
    machines: Sequence[QGroupMachine],
    queue: Sequence[QGroupJob],
    runtime: RuntimeCallback,
    fidelity: FidelityCallback,
    p: QGroupParameters = QGroupParameters(),
    compress: bool = True
) -> QGroupPlan:
    """Algorithm 4: Group machine types and call assign."""
    types = {}
    for machine in machines:
        types.setdefault((machine.type_key, machine.qubits), []).append(machine)
    return assign(list(types.values()), queue, runtime, fidelity, p, compress)


# ============================================================================
# Framework Integration
# ============================================================================

@dataclass
class QGroupBin:
    """A schedule group for framework integration."""
    machine_name: str
    jobs: dict[str, SchedulerJobInfo]
    start_time: float
    duration: float
    dispatch_order: int


class QGroup:
    """QGroup scheduling algorithm integrated with the quantum scheduling framework."""

    enable_optional_cutting: bool = False
    optional_cutting_policy: str = "half"

    def __init__(
        self,
        alpha: float = 0.25,
        delta: int = 1,
        eta: float = 1.0,
        runtime_scale: float = 0.748,
        overhead: float = 1.8,
        fidelity_weight: float = 1.0,
        time_limit: float | None = 30.0,
        enable_optional_cutting: bool = False,
        optional_cutting_policy: str = "half",
    ):
        """Initialize QGroup with configurable parameters."""
        self.enable_optional_cutting = enable_optional_cutting
        self.optional_cutting_policy = optional_cutting_policy
        self.params = QGroupParameters(
            alpha=alpha,
            delta=delta,
            eta=eta,
            runtime_scale=runtime_scale,
            overhead=overhead,
            fidelity_weight=fidelity_weight,
            time_limit=time_limit,
        )

    def execute(
        self,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> dict[str, SchedulerJobInfo]:
        """Execute QGroup scheduling algorithm."""
        if not scheduler_job:
            return scheduler_job

        qgroup_jobs = self._convert_jobs(scheduler_job)
        qgroup_machines = self._convert_machines(machines)

        plan = qgroup(
            machines=qgroup_machines,
            queue=qgroup_jobs,
            runtime=self._runtime_callback,
            fidelity=self._fidelity_callback,
            p=self.params,
            compress=True,
        )

        bins = self._convert_plan_to_bins(plan, scheduler_job, machines)
        self._assign_jobs(bins, machines)

        return scheduler_job

    def _convert_jobs(self, scheduler_job: dict[str, SchedulerJobInfo]) -> list[QGroupJob]:
        """Convert framework jobs to QGroup format."""
        qgroup_jobs = []
        for job_name, job in scheduler_job.items():
            job_info = job.job_information
            qubits = job_info.num_qubits if job_info.num_qubits is not None else job_info.circuit.num_qubits
            shots = job_info.shots if job_info.shots is not None else 1024
            qgroup_jobs.append(QGroupJob(id=job_name, qubits=qubits, shots=shots))
        return qgroup_jobs

    def _convert_machines(self, machines: dict[str, MachineCharacteristic]) -> list[QGroupMachine]:
        """Convert framework machines to QGroup format."""
        return [
            QGroupMachine(id=name, qubits=machine.capacity, type_key=machine.name, available_at=0.0)
            for name, machine in machines.items()
        ]

    def _runtime_callback(self, job: QGroupJob, machine: QGroupMachine) -> float:
        """Estimate runtime for a job on a machine."""
        base_time = 0.0001 * job.qubits * (job.shots / 1024)
        return base_time

    def _fidelity_callback(self, job: QGroupJob, machine: QGroupMachine, schedule: QGroupSchedule) -> float:
        """Estimate fidelity (EPST) for a job."""
        base_fidelity = 0.95
        qubit_penalty = (1.0 - 0.01 * job.qubits / machine.qubits)

        if hasattr(schedule, 'X') and schedule.X.size > 0:
            peak_util = max(
                sum(schedule.jobs[i].qubits * schedule.X[i, t] for i in range(len(schedule.jobs)))
                for t in range(schedule.X.shape[1])
            )
            workload_penalty = 1.0 - 0.005 * (peak_util / machine.qubits)
        else:
            workload_penalty = 1.0

        fidelity = base_fidelity * qubit_penalty * workload_penalty
        return max(0.01, min(1.0, fidelity))

    def _convert_plan_to_bins(
        self,
        plan: QGroupPlan,
        scheduler_job: dict[str, SchedulerJobInfo],
        machines: dict[str, MachineCharacteristic],
    ) -> list[QGroupBin]:
        """Convert QGroup plan to framework bins."""
        bins = []
        dispatch_order_per_machine = {machine_name: 0 for machine_name in machines}

        for machine_id, assignments in plan.assignments.items():
            for assignment in assignments:
                jobs_in_group = {}
                for job in assignment.schedule.jobs:
                    if job.id in scheduler_job:
                        jobs_in_group[job.id] = scheduler_job[job.id]

                if jobs_in_group:
                    bin_obj = QGroupBin(
                        machine_name=machine_id,
                        jobs=jobs_in_group,
                        start_time=assignment.start,
                        duration=assignment.finish - assignment.start,
                        dispatch_order=dispatch_order_per_machine[machine_id],
                    )
                    bins.append(bin_obj)
                    dispatch_order_per_machine[machine_id] += 1

        bins.sort(key=lambda b: b.start_time)
        return bins

    def _assign_jobs(
        self,
        bins: list[QGroupBin],
        machines: dict[str, MachineCharacteristic],
    ) -> None:
        """Update jobs with machine assignments and dependencies."""
        previous_bin_jobs: dict[str, list[JobInfo]] = {
            machine_name: [] for machine_name in machines
        }

        for bin_obj in bins:
            machine_name = bin_obj.machine_name

            for job in bin_obj.jobs.values():
                dependencies = self._merge_dependencies(
                    job.depends_on or [], previous_bin_jobs[machine_name]
                )
                job.assigned_machine = machine_name
                job.dispatch_order = bin_obj.dispatch_order
                job.depends_on = dependencies

            previous_bin_jobs[machine_name] = [
                job.job_information
                for job in bin_obj.jobs.values()
                if job.job_information is not None
            ]

    @staticmethod
    def _merge_dependencies(
        existing_dependencies: list[JobInfo | None],
        previous_bin_jobs: list[JobInfo],
    ) -> list[JobInfo | None]:
        """Merge and deduplicate dependencies."""
        dependencies: list[JobInfo | None] = []
        seen_ids: set[int] = set()
        for dependency in existing_dependencies + previous_bin_jobs:
            dependency_id = id(dependency)
            if dependency_id not in seen_ids:
                dependencies.append(dependency)
                seen_ids.add(dependency_id)
        return dependencies
