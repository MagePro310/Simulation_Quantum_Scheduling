"""Unified pipeline runner for quantum scheduling simulation algorithms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from source.algorithm.registry import get_algorithm
from source.flow.execution.orchestrator import ExecutionPhase
from source.flow.input.input_phase import InputPhase
from source.flow.schedule.schedule_phase import SchedulePhase
from source.models.schedule_result import ResultOfSchedule
from source.models.simulation_config import SimulationConfig
from source.utils.serialization import (
    print_schedule_result,
    serialize_result,
)


def run_pipeline(
    algorithm: Any,
    config: SimulationConfig | dict[str, Any] | str | Path | None = None,
    json_output: Path | str | None = None,
    gantt_output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute complete quantum scheduling pipeline for an algorithm instance or registered name.

    Uses SimulationConfig as the strict Single Source of Truth (SSOT).
    All simulation parameters (cutting policy, queue policy, seed, workload, machines)
    are derived exclusively from the configuration.

    Args:
        algorithm: Scheduling algorithm instance or registered name string (e.g. 'FFD').
        config: SimulationConfig instance, dict, or path to YAML/JSON config file.
        json_output: Optional path to save structured JSON results.
        gantt_output_path: Optional custom path to save Gantt chart PNG.

    Returns:
        Dictionary containing serialized scheduling and execution results.
    """
    if isinstance(algorithm, str):
        algo_instance = get_algorithm(algorithm)
    elif isinstance(algorithm, type):
        algo_instance = algorithm()
    else:
        algo_instance = algorithm

    # 1. Resolve configuration (Single Source of Truth)
    resolved_config = SimulationConfig.resolve(config)

    cutting_policy = resolved_config.scheduling.cutting_policy
    queue_policy = resolved_config.execution.queue_policy
    seed = resolved_config.execution.seed

    # 2. Initialize result schedule capture
    capture_result_schedule = ResultOfSchedule()

    # 3. Create input circuits and quantum machines driven strictly by config
    input_job, machines_set = InputPhase(config=resolved_config).create_input(capture_result_schedule)

    # 4. Schedule Phase:
    #    - Mandatory exceed cut: active for oversized circuits
    schedule_result = SchedulePhase(
        algorithm=algo_instance,
        exceed_cutting_policy=cutting_policy,
    ).execute(input_job, machines_set, capture_result_schedule)

    # 5. Execution Phase:
    #    - Discrete-event simulation, batch execution, and circuit reconstruction
    ExecutionPhase().execute(
        machines_set,
        schedule_result,
        queue_policy=queue_policy,
        seed=seed,
        gantt_output_path=str(gantt_output_path) if gantt_output_path else None,
        capture_result_schedule=capture_result_schedule,
    )

    # 6. Print scheduling results to terminal
    print_schedule_result(capture_result_schedule, schedule_result)

    # 7. Serialize and write JSON output if requested
    result_data = serialize_result(capture_result_schedule)
    if json_output:
        Path(json_output).write_text(json.dumps(result_data, indent=2), encoding="utf-8")
        print(f"\nJSON output written to: {json_output}")

    return result_data


def run_cli(
    algorithm_factory: Callable[[], Any] | str,
    description: str = "Quantum scheduling algorithm",
) -> None:
    """Standardized CLI entry point for algorithm simulations."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML/JSON simulation config file (default: configs/default_batch.yaml if present)",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Path to write structured JSON results",
    )
    parser.add_argument(
        "--gantt-output",
        type=Path,
        help="Custom path to save Gantt chart PNG",
    )
    args = parser.parse_args()

    algo = algorithm_factory() if callable(algorithm_factory) else algorithm_factory
    run_pipeline(
        algorithm=algo,
        config=args.config,
        json_output=args.json_output,
        gantt_output_path=args.gantt_output,
    )
