"""Run First Fit Decreasing Version 2 (FFD_v2) quantum scheduling algorithm.

Integrates proactive circuit chopping (half-cut) before scheduling to reduce QPU slack,
then re-orders all subcircuits decreasingly by size before bin packing.
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
from source.algorithm.heuristic.FFD_v2 import FFD_v2


def run_algorithm(
    json_output: Path | None = None,
    cutting_policy: str = "greedy",
    optional_cutting: bool = True,
    optional_cutting_policy: str = "half",
    queue_policy: str = "strict",
    seed: int = 0,
):
    """Run the FFD_v2 scheduling algorithm and optionally save results to JSON.

    Architecture & 2-Stage Cutting Workflow:
        1. Mandatory Exceed Cutting (Feasibility - Ban đầu):
           Circuits whose qubits exceed maximum machine capacity (qubits > max_capacity)
           are ALWAYS cut to ensure physical machine compatibility.
           Configured via `cutting_policy` (default: 'greedy').
        2. Proactive Cutting (Slack Minimization - Xong / Sau đó):
           All remaining uncut circuits (qubits >= 2) are proactively chopped using
           `optional_cutting_policy` (default: 'half') to reduce idle QPU space (slack).
           Active by default for FFD_v2 (`optional_cutting=True`).
        3. Bin Packing & Re-ordering:
           All resulting subcircuits are re-ordered largest-first and packed into machine bins
           using First Fit Decreasing.

    Args:
        json_output: Optional path to save JSON results for batch execution.
        cutting_policy: Mandatory cutting policy for oversized circuits ('greedy' or 'half', default: 'greedy').
        optional_cutting: Whether to apply proactive half-cutting to remaining circuits (default: True).
        optional_cutting_policy: Strategy for optional cutting ('half', default: 'half').
        queue_policy: Dispatch / backfilling policy ('strict' vs 'backfill').
        seed: Random seed for transpiler and simulator reproducibility.

    Returns:
        Execution results dictionary.
    """
    # 1. Initialize result schedule capture
    capture_result_schedule = ResultOfSchedule()

    # 2. Create input circuits and quantum machines
    input_job, machines_set = ConcreteInputPhase().create_input(capture_result_schedule)

    # 3. Instantiate algorithm
    algorithm = FFD_v2()

    # 4. Schedule Phase:
    #    - Mandatory exceed cut: always active for oversized circuits
    #    - Optional cut: active if optional_cutting=True
    schedule_result = ConcreteSchedulePhase(
        algorithm=algorithm,
        exceed_cutting_policy=cutting_policy,
        enable_optional_cutting=optional_cutting,
        optional_cutting_policy=optional_cutting_policy,
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
    parser = argparse.ArgumentParser(description="Run FFD_v2 quantum scheduling algorithm with autonomous chopping")
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
        "--optional-cutting",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable optional cutting for remaining eligible circuits (default: True for FFD_v2)",
    )
    parser.add_argument(
        "--optional-cutting-policy",
        type=str,
        choices=["half"],
        default="half",
        help="Policy for optional cutting stage: 'half' (default: 'half', extensible)",
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
        optional_cutting=args.optional_cutting,
        optional_cutting_policy=args.optional_cutting_policy,
        queue_policy=args.queue_policy,
        seed=args.seed,
    )

