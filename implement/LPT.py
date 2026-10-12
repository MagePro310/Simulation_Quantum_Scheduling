"""Run Longest Processing Time (LPT) quantum scheduling algorithm.

Sorts jobs by estimated execution duration (longest first) and assigns each job
to the least-loaded machine to minimize makespan.
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
from source.algorithm.heuristic.LPT import LPT


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    queue_policy: str = "strict",
    seed: int = 0,
    **kwargs,
):
    """Run the LPT scheduling algorithm and optionally save results to JSON."""
    # 1. Initialize result schedule capture
    capture_result_schedule = ResultOfSchedule()

    # 2. Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # 3. Instantiate algorithm
    algorithm = LPT()

    # 4. Schedule Phase:
    #    - Mandatory exceed cut: always active for oversized circuits
    schedule_result = ConcreteSchedulePhase(
        algorithm=algorithm,
        exceed_cutting_policy=cutting_policy,
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

    # 7. Serialize and write JSON output if requested
    result_data = serialize_result(capture_result_schedule)
    if json_output:
        Path(json_output).write_text(json.dumps(result_data, indent=2), encoding="utf-8")
        print(f"\nJSON output written to: {json_output}")

    return result_data


# Backward compatibility alias
test_concrete_flow = run_algorithm


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LPT quantum scheduling algorithm")
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
        help="Random seed for transpiler and simulation reproducibility",
    )
    args = parser.parse_args()

    run_algorithm(
        json_output=args.json_output,
        cutting_policy=args.cutting_policy,
        queue_policy=args.queue_policy,
        seed=args.seed,
    )

