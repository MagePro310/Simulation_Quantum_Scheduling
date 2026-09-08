"""Validate and normalize a fixed execution schedule without changing its inputs."""

from collections import deque
from dataclasses import dataclass
import math
from numbers import Real

from qiskit import QuantumCircuit

from source.component.dataclass.job_info import JobInfo, SchedulerJobInfo
from source.component.dataclass.machine_characteristic import MachineCharacteristic


@dataclass(frozen=True)
class ValidatedJob:
    information: JobInfo
    machine: str
    order: int
    shots: int
    arrival: float
    width: int
    dependencies: tuple[str, ...]


def _validate_options(queue_policy: str, seed: int) -> None:
    if queue_policy not in {"strict", "backfill"}:
        raise ValueError("queue_policy must be 'strict' or 'backfill'")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer between 0 and 2**32 - 1")


def _validate_machines(machines: dict[str, MachineCharacteristic]) -> None:
    for name, machine in machines.items():
        capacity = getattr(machine, "capacity", None)
        backend_width = getattr(getattr(machine, "quantum_machine", None), "num_qubits", None)
        if type(capacity) is not int or capacity <= 0:
            raise ValueError(f"Machine {name!r} must have a positive integer capacity")
        if not isinstance(backend_width, int) or backend_width < capacity:
            raise ValueError(f"Machine {name!r} capacity exceeds or lacks backend qubit width")


def _collect_job_identities(scheduler_job: dict[str, SchedulerJobInfo]) -> dict[int, str]:
    """Index dependency targets by identity, rejecting missing or shared JobInfo."""
    identities: dict[int, str] = {}
    for name, scheduled in scheduler_job.items():
        information = scheduled.job_information
        if information is None:
            raise ValueError(f"Job {name!r} has no job information")
        identity = id(information)
        if identity in identities:
            raise ValueError(
                f"Jobs {identities[identity]!r} and {name!r} share the same JobInfo identity"
            )
        identities[identity] = name
    return identities


def _validate_circuit(name: str, information: JobInfo) -> int:
    circuit = information.circuit
    if not isinstance(circuit, QuantumCircuit) or circuit.num_qubits <= 0:
        raise ValueError(f"Job {name!r} must have a nonempty QuantumCircuit")
    if circuit.num_parameters:
        raise ValueError(f"Job {name!r} has unbound circuit parameters")
    if not circuit.num_clbits or not any(
        instruction.operation.name == "measure" for instruction in circuit.data
    ):
        raise ValueError(f"Job {name!r} must have measurements and classical result bits")
    width = circuit.num_qubits
    if information.num_qubits is not None and (
        type(information.num_qubits) is not int or information.num_qubits != width
    ):
        raise ValueError(f"Job {name!r} num_qubits does not match its circuit width")
    return width


def _validate_dependencies(
    name: str,
    scheduled: SchedulerJobInfo,
    identities: dict[int, str],
) -> tuple[str, ...]:
    dependencies: list[str] = []
    for dependency in scheduled.depends_on or []:
        dependency_name = identities.get(id(dependency))
        if dependency_name is None:
            raise ValueError(f"Job {name!r} has an unknown dependency outside the workload")
        if dependency_name == name:
            raise ValueError(f"Job {name!r} has a self-dependency")
        if dependency_name not in dependencies:
            dependencies.append(dependency_name)
    return tuple(dependencies)


def _validate_job(
    name: str,
    scheduled: SchedulerJobInfo,
    machines: dict[str, MachineCharacteristic],
    orders: dict[str, set[int]],
    identities: dict[int, str],
) -> ValidatedJob:
    information = scheduled.job_information
    width = _validate_circuit(name, information)
    machine_name = scheduled.assigned_machine
    if machine_name not in machines:
        raise ValueError(f"Job {name!r} has unknown assigned machine {machine_name!r}")
    if width > machines[machine_name].capacity:
        raise ValueError(f"Job {name!r} exceeds capacity on machine {machine_name!r}")
    order = scheduled.dispatch_order
    if type(order) is not int or order < 0:
        raise ValueError(f"Job {name!r} must have a nonnegative integer dispatch_order")
    if order in orders[machine_name]:
        raise ValueError(f"Duplicate dispatch_order {order} on machine {machine_name!r}")
    orders[machine_name].add(order)
    shots = 1024 if information.shots is None else information.shots
    if type(shots) is not int or shots <= 0:
        raise ValueError(f"Job {name!r} must have a positive integer shot count")
    arrival = 0 if information.arrival_time is None else information.arrival_time
    if isinstance(arrival, bool) or not isinstance(arrival, Real):
        raise ValueError(f"Job {name!r} arrival_time must be finite and nonnegative")
    try:
        arrival = float(arrival)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"Job {name!r} arrival_time must be finite and nonnegative") from error
    if not math.isfinite(arrival) or arrival < 0:
        raise ValueError(f"Job {name!r} arrival_time must be finite and nonnegative")
    dependencies = _validate_dependencies(name, scheduled, identities)
    return ValidatedJob(information, machine_name, order, shots, arrival, width, dependencies)


def _assert_acyclic(
    jobs: dict[str, ValidatedJob], queues: dict[str, list[str]], strict: bool
) -> None:
    successors: dict[str, set[str]] = {name: set() for name in jobs}
    for name, job in jobs.items():
        for dependency in job.dependencies:
            successors[dependency].add(name)
    if strict:
        # These edges constrain admission order, not serial completion.
        for queue in queues.values():
            for previous, following in zip(queue, queue[1:]):
                successors[previous].add(following)
    indegrees = {name: 0 for name in jobs}
    for children in successors.values():
        for child in children:
            indegrees[child] += 1
    ready = deque(name for name, degree in indegrees.items() if degree == 0)
    while ready:
        for child in successors[ready.popleft()]:
            indegrees[child] -= 1
            if indegrees[child] == 0:
                ready.append(child)
    unresolved = [name for name, degree in indegrees.items() if degree]
    if unresolved:
        kind = "dependency or strict dispatch-order" if strict else "dependency"
        raise ValueError(f"Schedule has a {kind} cycle involving jobs: {unresolved}")


def validate_schedule(
    machines: dict[str, MachineCharacteristic],
    scheduler_job: dict[str, SchedulerJobInfo],
    queue_policy: str,
    seed: int,
) -> tuple[dict[str, ValidatedJob], dict[str, list[str]]]:
    """Normalize jobs and ordered machine queues after checking the whole plan."""
    _validate_options(queue_policy, seed)
    _validate_machines(machines)
    identities = _collect_job_identities(scheduler_job)

    jobs: dict[str, ValidatedJob] = {}
    queues: dict[str, list[str]] = {name: [] for name in machines}
    orders: dict[str, set[int]] = {name: set() for name in machines}
    for name, scheduled in scheduler_job.items():
        job = _validate_job(name, scheduled, machines, orders, identities)
        jobs[name] = job
        queues[job.machine].append(name)

    for queue in queues.values():
        queue.sort(key=lambda name: jobs[name].order)
    _assert_acyclic(jobs, queues, strict=queue_policy == "strict")
    return jobs, queues
