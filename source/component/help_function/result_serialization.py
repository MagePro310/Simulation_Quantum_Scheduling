"""Serialize scheduling results for JSON output."""

from source.component.dataclass.result_schedule import ResultOfSchedule


def serialize_result(capture_result_schedule: ResultOfSchedule) -> dict:
    """Convert ResultOfSchedule to JSON-serializable dictionary."""
    result_dict = {
        "numCircuits": capture_result_schedule.numCircuits,
        "nameCircuits": capture_result_schedule.nameCircuits,
        "averageQubits": capture_result_schedule.averageQubits,
        "nameMachines": capture_result_schedule.nameMachines,
        "nameSchedule": capture_result_schedule.nameSchedule,
        "ScheduleLatency": capture_result_schedule.ScheduleLatency,
    }

    # Serialize execution summary if present
    if capture_result_schedule.execution_summary:
        exec_sum = capture_result_schedule.execution_summary

        # Serialize batches (convert BatchExecutionRecord objects to dicts)
        batches_serialized = []
        for batch in exec_sum.batches:
            batch_dict = {
                "batch_id": batch.batch_id,
                "machine_name": batch.machine_name,
                "job_ids": list(batch.job_ids),  # Convert tuple to list
                "shots": batch.shots,
                "start_time": batch.start_time,
                "end_time": batch.end_time,
                "logical_qubits": batch.logical_qubits,
                "status": batch.status,
                "error_reason": batch.error_reason,
            }
            batches_serialized.append(batch_dict)

        result_dict["execution_summary"] = {
            "makespan": exec_sum.makespan,
            "total_turnaround_time": exec_sum.total_turnaround_time,
            "total_waiting_time": exec_sum.total_waiting_time,
            "total_response_time": exec_sum.total_response_time,
            "average_turnaround_time": exec_sum.average_turnaround_time,
            "average_waiting_time": exec_sum.average_waiting_time,
            "average_response_time": exec_sum.average_response_time,
            "job_completion_rate": exec_sum.job_completion_rate,
            "average_fidelity": exec_sum.average_fidelity,
            "succeeded_jobs": exec_sum.succeeded_jobs,
            "failed_jobs": exec_sum.failed_jobs,
            "blocked_jobs": exec_sum.blocked_jobs,
            "machines": {
                name: {
                    "machine_name": m.machine_name,
                    "utilization": m.utilization,
                    "busy_time": m.busy_time,
                    "qubit_time": m.qubit_time,
                }
                for name, m in exec_sum.machines.items()
            },
            "batches": batches_serialized,
        }
    else:
        result_dict["execution_summary"] = None

    # Add metadata
    result_dict["seed"] = 0
    result_dict["queue_policy"] = "strict"
    result_dict["workload_fingerprint"] = f"{capture_result_schedule.numCircuits}_{capture_result_schedule.nameCircuits}"
    result_dict["machine_config"] = str(capture_result_schedule.nameMachines)

    # Add dependency versions
    import qiskit
    import numpy
    import matplotlib
    result_dict["dependency_versions"] = {
        "qiskit": qiskit.__version__,
        "numpy": numpy.__version__,
        "matplotlib": matplotlib.__version__,
    }

    return result_dict
