"""Centralized simulation configuration dataclasses for quantum scheduling.

Provides a Single Source of Truth (SSOT) for all workload, machine,
scheduling, execution, and batch parameters, loaded from YAML or JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default_batch.yaml"

VALID_CUTTING_POLICIES = {"greedy", "half"}
VALID_QUEUE_POLICIES = {"strict", "relaxed", "backfill"}


@dataclass
class WorkloadConfig:
    """Configuration for circuit jobs workload."""
    benchmark: str = "ghz"
    jobs: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        "job1": {"qubits": 2, "shots": 1024, "arrival_time": 0, "priority": 1},
        "job2": {"qubits": 2, "shots": 1024, "arrival_time": 0, "priority": 1},
        "job3": {"qubits": 3, "shots": 1024, "arrival_time": 0, "priority": 1},
        "job4": {"qubits": 7, "shots": 1024, "arrival_time": 0, "priority": 1},
    })
    generator: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.benchmark:
            raise ValueError("Workload benchmark name must not be empty.")
        if not self.jobs and not self.generator:
            raise ValueError(
                "Workload configuration must specify either 'jobs' (explicit circuit list) "
                "or 'generator' (automated circuit synthesis parameters)."
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WorkloadConfig:
        if not data:
            return cls()
        default_inst = cls()
        benchmark = data.get("benchmark", default_inst.benchmark)
        generator = data.get("generator")
        jobs = data.get("jobs")
        if jobs is None:
            jobs = {} if generator else default_inst.jobs
        return cls(
            benchmark=benchmark,
            jobs=jobs,
            generator=generator,
        )


@dataclass
class SchedulingConfig:
    """Configuration for scheduling policies and circuit cutting."""
    cutting_policy: str = "greedy"  # 'greedy' or 'half'

    def __post_init__(self) -> None:
        self.cutting_policy = self.cutting_policy.lower()
        if self.cutting_policy not in VALID_CUTTING_POLICIES:
            raise ValueError(
                f"Invalid cutting_policy '{self.cutting_policy}'. "
                f"Allowed policies: {sorted(VALID_CUTTING_POLICIES)}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SchedulingConfig:
        if not data:
            return cls()
        return cls(
            cutting_policy=data.get("cutting_policy", "greedy"),
        )


@dataclass
class ExecutionConfig:
    """Configuration for simulator execution, queue policy, and reproducibility."""
    seed: int = 0
    queue_policy: str = "strict"  # 'strict', 'relaxed', or 'backfill'
    timeout: int = 600

    def __post_init__(self) -> None:
        self.queue_policy = self.queue_policy.lower()
        if self.queue_policy not in VALID_QUEUE_POLICIES:
            raise ValueError(
                f"Invalid queue_policy '{self.queue_policy}'. "
                f"Allowed policies: {sorted(VALID_QUEUE_POLICIES)}"
            )
        if self.seed < 0:
            raise ValueError(f"Random seed must be a non-negative integer, got {self.seed}.")
        if self.timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {self.timeout}.")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecutionConfig:
        if not data:
            return cls()
        return cls(
            seed=int(data.get("seed", 0)),
            queue_policy=str(data.get("queue_policy", "strict")),
            timeout=int(data.get("timeout", 600)),
        )


@dataclass
class BatchConfig:
    """Configuration for batch runner and comparison reporting."""
    algorithms: list[str] = field(default_factory=lambda: [
        "FFD",
        "FFD_v2",
        "Adaptive_FFD",
        "LPT",
        "QGroup",
    ])
    auto_compare: bool = True
    output_dir: str = "results"

    def __post_init__(self) -> None:
        if not self.algorithms:
            raise ValueError("Batch algorithms list must not be empty.")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BatchConfig:
        if not data:
            return cls()
        return cls(
            algorithms=list(data.get("algorithms", [
                "FFD", "FFD_v2", "Adaptive_FFD", "LPT", "QGroup"
            ])),
            auto_compare=bool(data.get("auto_compare", True)),
            output_dir=str(data.get("output_dir", "results")),
        )


@dataclass
class SimulationConfig:
    """Top-level simulation configuration unifying all components (Single Source of Truth)."""
    workload: WorkloadConfig = field(default_factory=WorkloadConfig)
    machines: list[str] = field(default_factory=lambda: [
        "FakeBelemV2",
        "FakeBogotaV2",
    ])
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)

    def __post_init__(self) -> None:
        if not self.machines:
            raise ValueError("SimulationConfig machines list must not be empty.")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SimulationConfig:
        """Create SimulationConfig from dictionary."""
        if not data:
            return cls()
        return cls(
            workload=WorkloadConfig.from_dict(data.get("workload")),
            machines=list(data.get("machines", ["FakeBelemV2", "FakeBogotaV2"])),
            scheduling=SchedulingConfig.from_dict(data.get("scheduling")),
            execution=ExecutionConfig.from_dict(data.get("execution")),
            batch=BatchConfig.from_dict(data.get("batch")),
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> SimulationConfig:
        """Load configuration from a YAML file."""
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def save_yaml(self, path: Path | str) -> None:
        """Save configuration to a YAML file."""
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, sort_keys=False)

    @classmethod
    def find_default_config(cls) -> Path | None:
        """Locate default config file in PROJECT_ROOT / configs / default_batch.yaml."""
        if DEFAULT_CONFIG_PATH.exists():
            return DEFAULT_CONFIG_PATH
        return None

    @classmethod
    def resolve(cls, config_input: SimulationConfig | dict[str, Any] | str | Path | None = None) -> SimulationConfig:
        """Resolve config from any supported input type (None, path, dict, or instance).

        If config_input is None, attempts to auto-load configs/default_batch.yaml.
        If that file does not exist, returns standard defaults.
        """
        if isinstance(config_input, cls):
            return config_input

        if isinstance(config_input, (str, Path)):
            return cls.from_yaml(config_input)

        if isinstance(config_input, dict):
            return cls.from_dict(config_input)

        # When config_input is None, check for default YAML file
        default_file = cls.find_default_config()
        if default_file and default_file.exists():
            return cls.from_yaml(default_file)

        return cls()
