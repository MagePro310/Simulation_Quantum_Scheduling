"""QGroup quantum scheduling algorithm implementation.

Integrates the QGroup Algorithms 1-4 (Orenstein & Chaudhary, QCE 2024)
into the quantum scheduling framework.
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


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    cutting_scope: str = "exceed",
    cut_all: bool | None = None,
):
    """Run the QGroup scheduling algorithm and optionally save results to JSON."""

    # Initialize result_Schedule
    capture_result_schedule = ResultOfSchedule()

    # Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # Import QGroup algorithm
    from source.algorithm.heuristic.QGroup import QGroup
    algorithm = QGroup()

    # Schedule Phase
    schedule_result = ConcreteSchedulePhase(
        algorithm=algorithm,
        cutting_policy=cutting_policy,
        cutting_scope=cutting_scope,
        cut_all=cut_all,
    ).execute(
        input_job, machines_set, capture_result_schedule
    )

    # Execution Phase
    results = ConcreteExecutionPhase().execute(
        machines_set, schedule_result, capture_result_schedule=capture_result_schedule
    )

    # Print scheduling results to terminal
    print_schedule_result(capture_result_schedule, schedule_result)

    # Write JSON output if requested
    if json_output:
        result_data = serialize_result(capture_result_schedule)
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
        print(f"\nJSON output written to: {json_output}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run QGroup quantum scheduling algorithm")
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Path to write structured JSON results for batch processing"
    )
    parser.add_argument(
        "--cutting-policy",
        type=str,
        choices=["greedy", "half"],
        default="greedy",
        help="Circuit cutting policy: 'greedy' (max capacity chunks) or 'half' (split in half)"
    )
    parser.add_argument(
        "--cutting-scope",
        type=str,
        choices=["exceed", "all"],
        default="exceed",
        help="In half cut policy, cut 'all' circuits or only circuits that 'exceed' machine capacity (default: 'exceed')"
    )
    parser.add_argument(
        "--cut-all",
        action="store_true",
        default=False,
        help="Shorthand to cut all circuits in half policy (--cutting-scope all)"
    )
    args = parser.parse_args()

    cutting_scope = "all" if args.cut_all else args.cutting_scope
    run_algorithm(
        json_output=args.json_output,
        cutting_policy=args.cutting_policy,
        cutting_scope=cutting_scope,
    )
