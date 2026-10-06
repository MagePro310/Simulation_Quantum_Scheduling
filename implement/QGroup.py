"""Run QGroup quantum scheduling algorithm.

Groups quantum circuits by resource similarity and scheduled execution windows.
"""

import sys
import json
import argparse
from pathlib import Path

# Support running this script directly from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source.component.help_function.result_serialization import serialize_result, print_schedule_result
from source.component.dataclass.result_schedule import ResultOfSchedule
from source.flow.input.phase_input import ConcreteInputPhase
from source.flow.schedule.phase_schedule import ConcreteSchedulePhase
from source.flow.execution.orchestrator import ConcreteExecutionPhase
from source.algorithm.heuristic.QGroup import QGroup


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    cutting_scope: str = "exceed",
    cut_all: bool | None = None,
    queue_policy: str = "strict",
    seed: int = 0,
):
    """Run the QGroup scheduling algorithm and optionally save results to JSON.

    Args:
        json_output: Optional path to save JSON results for batch execution.
        cutting_policy: Mandatory cutting policy for oversized circuits ('greedy' or 'half').
        cutting_scope: Compatibility parameter for cutting scope ('exceed' or 'all').
        cut_all: Compatibility flag to cut all circuits.
        queue_policy: Dispatch/backfilling policy ('strict', 'relaxed', 'backfill').
        seed: Random seed for transpiler and simulator reproducibility.

    Returns:
        Execution results dictionary.
    """
    # 1. Initialize result schedule capture
    capture_result_schedule = ResultOfSchedule()

    # 2. Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # 3. Instantiate algorithm
    algorithm = QGroup()

    # 4. Schedule Phase (PreSchedule feasibility check + algorithm scheduling)
    schedule_result = ConcreteSchedulePhase(
        algorithm=algorithm,
        cutting_policy=cutting_policy,
    ).execute(input_job, machines_set, capture_result_schedule)

    # 5. Execution Phase (simulation / backend execution & reconstruction)
    results = ConcreteExecutionPhase().execute(
        machines_set,
        schedule_result,
        queue_policy=queue_policy,
        seed=seed,
        capture_result_schedule=capture_result_schedule,
    )

    # 6. Print scheduling results to terminal
    print_schedule_result(capture_result_schedule, schedule_result)

    # 7. Write JSON output if requested
    if json_output:
        result_data = serialize_result(capture_result_schedule)
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
        print(f"\nJSON output written to: {json_output}")

    return results


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run QGroup quantum scheduling algorithm")
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
        help="Mandatory circuit cutting policy for oversized circuits: 'greedy' or 'half'",
    )
    parser.add_argument(
        "--cutting-scope",
        type=str,
        choices=["exceed", "all"],
        default="exceed",
        help="Cutting scope for compatibility: 'exceed' (default) or 'all'",
    )
    parser.add_argument(
        "--cut-all",
        action="store_true",
        default=False,
        help="Legacy shorthand to cut all circuits",
    )
    parser.add_argument(
        "--queue-policy",
        type=str,
        choices=["strict", "relaxed", "backfill"],
        default="strict",
        help="Queue dispatch / backfilling policy: 'strict', 'relaxed', or 'backfill'",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for transpiler and simulation reproducibility",
    )
    args = parser.parse_args()

    run_algorithm(
        json_output=args.json_output,
        cutting_policy=args.cutting_policy,
        cutting_scope=args.cutting_scope,
        cut_all=args.cut_all,
        queue_policy=args.queue_policy,
        seed=args.seed,
    )
