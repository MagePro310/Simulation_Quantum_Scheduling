# Refactoring Plan: source/flow/execution/

## Goal
Refactor the execution folder to improve readability, reduce complexity, and eliminate unnecessary validation overhead by removing `ValidatedJob` and inlining validation logic.

## Current Structure Analysis

### Files (960 total lines):
1. **phase_execution.py** (350 lines) - Main orchestrator with complex event loop
2. **execution_validation.py** (179 lines) - Creates intermediate `ValidatedJob` dataclass
3. **post_execution_analysis.py** (239 lines) - Result processing + visualization
4. **pre_execution_transpile.py** (106 lines) - Circuit preparation
5. **main_execution_quantum.py** (86 lines) - Quantum simulation

### Problems Identified:
1. **ValidatedJob creates unnecessary duplication** - copies data from `SchedulerJobInfo` → `ValidatedJob` → used only in `phase_execution.py`
2. **phase_execution.py is too complex** - 350 lines mixing orchestration, state management, event handling, and validation
3. **Validation scattered** - in execution_validation.py, pre_execution_transpile.py, and phase_execution.py
4. **Hard to debug** - state transitions buried in long methods
5. **Visualization mixed with analysis** - gantt chart generation in same file as metrics

### External Dependencies:
- **main.py** imports `ConcreteExecutionPhase`
- **tests/test_execution_phase.py** imports `ConcreteExecutionPhase`
- **tests/test_execution_analysis.py** imports `ConcreteExecutionPhase` and `PostExecution`
- **tests/test_execution_quantum.py** imports `PreExecution` and `MainExecutionQuantum`

## Proposed Structure

```
source/flow/execution/
├── __init__.py                          # Public API exports
├── orchestrator.py                      # Main entry (replaces ConcreteExecutionPhase)
│
├── preparation/
│   ├── __init__.py
│   └── circuit_preparation.py          # Circuit transpilation (from pre_execution_transpile.py)
│
├── simulation/
│   ├── __init__.py
│   └── quantum_executor.py             # Quantum simulation (from main_execution_quantum.py)
│
├── coordination/
│   ├── __init__.py
│   ├── execution_state.py              # State models and dataclasses
│   ├── event_scheduler.py              # Event loop and time management
│   └── batch_manager.py                # Batch lifecycle (prepare → submit → complete)
│
└── analysis/
    ├── __init__.py
    ├── metrics_calculator.py           # Result processing and metrics
    └── gantt_visualizer.py             # Gantt chart generation
```

**Note:** Validation is completely removed from the execution flow. The orchestrator will work directly with `SchedulerJobInfo` and handle errors gracefully during execution.

## Detailed Changes

### 1. Remove ValidatedJob Dataclass and All Validation
**Current flow:**
```
SchedulerJobInfo → validate_schedule() → ValidatedJob → _ExecutionRun
```

**New flow:**
```
SchedulerJobInfo → _ExecutionRun (uses SchedulerJobInfo directly, fail-fast during execution)
```

**Changes:**
- Delete `ValidatedJob` class entirely
- Delete `execution_validation.py` - no upfront validation
- Remove all validation logic from the flow
- Use `SchedulerJobInfo` directly in `_ExecutionRun`
- Let errors surface naturally during preparation/execution (fail-fast approach)
- Circuit validation stays in `circuit_preparation.py` (happens during prepare_batch)
- Shot validation stays in `quantum_executor.py` (happens during execute_batch)

### 2. Split phase_execution.py (350 lines → ~100 + distributed)

**orchestrator.py** (~100 lines):
- `ConcreteExecutionPhase` class (public API)
- `execute()` method (high-level flow)
- Dependency injection for helpers
- Summary printing

**coordination/execution_state.py** (~50 lines):
- `_MachineState` dataclass
- `_Completion` dataclass
- `_ExecutionRun` dataclass
- Status constants

**coordination/event_scheduler.py** (~80 lines):
- `_run_until_finished()` logic
- `_finish_due_batches()`
- `_next_event_time()` and `_next_timestamp()`
- Event heap management

**coordination/batch_manager.py** (~120 lines):
- `_dispatch_ready_machines()`
- `_admit_jobs()`
- `_prepare_batch()`
- `_submit_batch()`
- `_complete_batch()`
- `_fail_preparation()`
- `_block_dependents()`

### 3. Remove validation completely (179 lines deleted)

**No validation phase:**
- Delete entire `execution_validation.py` file
- Remove all upfront validation from orchestrator
- Trust that scheduler provides valid assignments
- Fail gracefully during execution if issues arise
- Existing validations in preparation and simulation remain (they're part of those operations)

### 4. Split post_execution_analysis.py (239 lines → 160 + 80)

**analysis/metrics_calculator.py** (~160 lines):
- `MetricsCalculator` class (rename from `PostExecution`)
- `split_counts()` method
- `finalize()` method (without gantt generation)
- `_populate_job_metrics()`
- `_populate_machine_metrics()`
- All validation methods

**analysis/gantt_visualizer.py** (~80 lines):
- `GanttVisualizer` class
- `draw_gantt_chart()` method
- Matplotlib logic isolated

### 5. Rename and move other files

**simulation/quantum_executor.py** (86 lines, unchanged logic):
- Rename `MainExecutionQuantum` → `QuantumExecutor`
- Keep all existing methods

**preparation/circuit_preparation.py** (106 lines, unchanged logic):
- Rename `PreExecution` → `CircuitPreparation`
- Keep all existing methods

### 6. Create clean public API

**source/flow/execution/__init__.py**:
```python
"""Quantum job execution phase."""

from source.flow.execution.orchestrator import ConcreteExecutionPhase
from source.flow.execution.simulation.quantum_executor import QuantumExecutor
from source.flow.execution.preparation.circuit_preparation import CircuitPreparation
from source.flow.execution.analysis.metrics_calculator import MetricsCalculator
from source.flow.execution.analysis.gantt_visualizer import GanttVisualizer

__all__ = [
    "ConcreteExecutionPhase",
    "QuantumExecutor",
    "CircuitPreparation",
    "MetricsCalculator",
    "GanttVisualizer",
]
```

## Implementation Steps

### Phase 1: Create new structure (no breaking changes yet)
1. Create folder structure: `preparation/`, `simulation/`, `coordination/`, `analysis/`
2. Create all `__init__.py` files
3. Copy `main_execution_quantum.py` → `simulation/quantum_executor.py` (keep both)
4. Copy `pre_execution_transpile.py` → `preparation/circuit_preparation.py` (keep both)

### Phase 2: Remove validation (DELETED)
5. ~~No validation extraction needed~~
6. Delete `execution_validation.py` completely
7. Remove all references to `validate_schedule()` and `ValidatedJob`

### Phase 3: Split phase_execution.py
8. Create `coordination/execution_state.py` with dataclasses and constants
9. Create `coordination/event_scheduler.py` with event loop logic
10. Create `coordination/batch_manager.py` with batch lifecycle methods
11. Create `orchestrator.py` that imports and uses the extracted components
12. Remove `ValidatedJob` - use `SchedulerJobInfo` directly in orchestrator

### Phase 4: Split post_execution_analysis.py
13. Create `analysis/metrics_calculator.py` with core metrics logic
14. Create `analysis/gantt_visualizer.py` with plotting logic
15. Update orchestrator to use new metrics calculator

### Phase 5: Clean up and update imports
16. Update `__init__.py` to export new classes
17. Delete old files: `execution_validation.py` (FIRST), `phase_execution.py`, `post_execution_analysis.py`, `main_execution_quantum.py`, `pre_execution_transpile.py`
18. Update imports in `main.py`
19. Update test files - remove all validation tests from `test_execution_phase.py`

### Phase 6: Verify tests
20. Run all execution tests
21. Fix any import or logic issues
22. Verify gantt chart generation still works

## Benefits

### Readability
- Each file has single responsibility
- ~100-160 lines per file (down from 350)
- Clear separation: preparation → execution → analysis
- Easy to find specific functionality
- **No validation complexity** - simpler flow

### Maintainability
- **No validation layer** - one less thing to maintain
- State management isolated
- Event loop logic separate from business logic
- Visualization isolated from metrics
- Trust scheduler output, fail-fast if needed

### Debuggability
- Clear state transitions in `execution_state.py`
- Event handling isolated in `event_scheduler.py`
- Can add logging per module easily
- Smaller files easier to read during debugging
- **Errors happen at point of use** - easier to trace

### Performance
- **Eliminate ValidatedJob dataclass** - no intermediate objects
- **Eliminate 179 lines of validation overhead** - direct execution
- No upfront validation pass through all jobs
- Fail-fast only when actually needed

## Risk Mitigation

1. **Keep backward compatibility initially** - old files stay until new ones proven
2. **Comprehensive test coverage** - all 3 test files must pass
3. **No logic changes** - pure refactoring, only structure changes
4. **Incremental approach** - can stop at any phase if issues arise
5. **Easy rollback** - old files kept until final deletion step

## Success Criteria

- ✅ All tests pass (test_execution_phase.py, test_execution_quantum.py, test_execution_analysis.py)
- ✅ main.py runs successfully
- ✅ No file exceeds 200 lines
- ✅ ValidatedJob removed completely
- ✅ Clear module boundaries with focused responsibilities
- ✅ Public API unchanged (`ConcreteExecutionPhase` still works)
