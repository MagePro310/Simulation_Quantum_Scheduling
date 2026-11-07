"""Unified pipeline runner for quantum scheduling simulation algorithms."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.component.dataclass.result_schedule import ResultOfSchedule
from source.component.help_function.result_serialization import (
    print_schedule_result,
    serialize_result,
)
from source.flow.execution.orchestrator import ConcreteExecutionPhase
from source.flow.input.phase_input import ConcreteInputPhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase


def run_pipeline(
    algorithm: Any,
    json_output: Path | str | None = None,
    cutting_policy: str = "greedy",
    queue_policy: str = "strict",
    seed: int = 0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute complete quantum scheduling pipeline for an algorithm instance.

    Args:
        algorithm: Scheduling algorithm instance (must implement execute()).
        json_output: Optional path to save structured JSON results.
        cutting_policy: Mandatory cutting policy for oversized circuits ('greedy' or 'half').
        queue_policy: Queue dispatch / backfilling policy ('strict' vs 'backfill').
        seed: Random seed for transpiler and simulator reproducibility.
        **kwargs: Extra parameters reserved for future extensions.

    Returns:
        Dictionary containing serialized scheduling and execution results.
    """
    # 1. Initialize result schedule capture
    capture_result_schedule = ResultOfSchedule()

    # 2. Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # 3. Schedule Phase:
    #    - Mandatory exceed cut: active for oversized circuits
    schedule_result = ConcreteSchedulePhase(
        algorithm=algorithm,
        exceed_cutting_policy=cutting_policy,
    ).execute(input_job, machines_set, capture_result_schedule)

    # 4. Execution Phase:
    #    - Discrete-event simulation, batch execution, and circuit reconstruction
    results = ConcreteExecutionPhase().execute(
        machines_set,
        schedule_result,
        queue_policy=queue_policy,
        seed=seed,
        capture_result_schedule=capture_result_schedule,
    )

    # 5. Print scheduling results to terminal
    print_schedule_result(capture_result_schedule, schedule_result)

    # 6. Serialize and write JSON output if requested
    result_data = serialize_result(capture_result_schedule)
    if json_output:
        Path(json_output).write_text(json.dumps(result_data, indent=2), encoding="utf-8")
        print(f"\nJSON output written to: {json_output}")

    return result_data


def run_cli(
    algorithm_factory: Callable[[], Any],
    description: str = "Quantum scheduling algorithm",
) -> None:
    """Standardized CLI entry point for standalone algorithm scripts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Path to write structured JSON results for batch processing",
    )
    parser.add_argument(
        "--cutting-policy",
        type=str,
        choices=["greedy", "half"],
        default="greedy",
        help="Mandatory cut policy for circuits exceeding machine capacity: 'greedy' or 'half' (default: 'greedy')",
    )
    parser.add_argument(
        "--queue-policy",
        type=str,
        choices=["strict", "backfill"],
        default="strict",
        help="Queue dispatch / backfilling policy: 'strict' or 'backfill' (default: 'strict')",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for transpiler and simulation reproducibility (default: 0)",
    )
    args = parser.parse_args()

    run_pipeline(
        algorithm=algorithm_factory(),
        json_output=args.json_output,
        cutting_policy=args.cutting_policy,
        queue_policy=args.queue_policy,
        seed=args.seed,
    )
