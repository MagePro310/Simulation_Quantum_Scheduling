"""Centralized simulation configuration dataclasses for quantum scheduling.

Provides a Single Source of Truth (SSOT) for all workload, machine,
scheduling, execution, and batch parameters, loaded from YAML or JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default_batch.yaml"

VALID_CUTTING_POLICIES = {"greedy", "half"}
VALID_QUEUE_POLICIES = {"strict", "backfill"}


@dataclass
class WorkloadConfig:
    """Configuration for circuit jobs workload."""

    benchmark: str = "ghz"
    jobs: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "job1": {"qubits": 2, "shots": 1024, "arrival_time": 0, "priority": 1},
            "job2": {"qubits": 2, "shots": 1024, "arrival_time": 0, "priority": 1},
            "job3": {"qubits": 3, "shots": 1024, "arrival_time": 0, "priority": 1},
            "job4": {"qubits": 7, "shots": 1024, "arrival_time": 0, "priority": 1},
        }
    )
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
    queue_policy: str = "strict"  # 'strict' or 'backfill'
    timeout: int = 600
    # Wait between shots, in seconds. None uses each backend's default_rep_delay
    # (250 us on the IBM fake backends), which dominates a shot's time.
    rep_delay: float | None = None

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
        if self.rep_delay is not None and self.rep_delay < 0:
            raise ValueError(f"rep_delay must be non-negative seconds, got {self.rep_delay}.")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecutionConfig:
        if not data:
            return cls()
        return cls(
            seed=int(data.get("seed", 0)),
            queue_policy=data.get("queue_policy", "strict"),
            timeout=int(data.get("timeout", 600)),
            rep_delay=None if data.get("rep_delay") is None else float(data["rep_delay"]),
        )


@dataclass
class BatchConfig:
    """Configuration for batch simulation runner and automated reporting."""

    algorithms: list[str] = field(
        default_factory=lambda: ["FFD", "FFD_v2", "Adaptive_FFD", "LPT", "QGroup"]
    )
    auto_compare: bool = True
    output_dir: str = "results"

    def __post_init__(self) -> None:
        if not self.algorithms:
            raise ValueError("Batch algorithms list must contain at least one algorithm.")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BatchConfig:
        if not data:
            return cls()
        return cls(
            algorithms=list(data.get("algorithms", ["FFD", "FFD_v2", "Adaptive_FFD", "LPT", "QGroup"])),
            auto_compare=bool(data.get("auto_compare", True)),
            output_dir=str(data.get("output_dir", "results")),
        )


@dataclass
class SimulationConfig:
    """Centralized root configuration serving as Single Source of Truth (SSOT)."""

    workload: WorkloadConfig = field(default_factory=WorkloadConfig)
    machines: list[str] = field(default_factory=lambda: ["FakeBelemV2", "FakeBogotaV2"])
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)

    def __post_init__(self) -> None:
        if not self.machines:
            raise ValueError("SimulationConfig machines list must not be empty.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationConfig:
        """Create SimulationConfig from dictionary."""
        return cls(
            workload=WorkloadConfig.from_dict(data.get("workload")),
            machines=list(data.get("machines", ["FakeBelemV2", "FakeBogotaV2"])),
            scheduling=SchedulingConfig.from_dict(data.get("scheduling")),
            execution=ExecutionConfig.from_dict(data.get("execution")),
            batch=BatchConfig.from_dict(data.get("batch")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to nested dictionary."""
        return asdict(self)

    @classmethod
    def from_json(cls, path: Path | str) -> SimulationConfig:
        """Load configuration from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def save_json(self, path: Path | str) -> None:
        """Save configuration to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_yaml(cls, path: Path | str) -> SimulationConfig:
        """Load configuration from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def save_yaml(self, path: Path | str) -> None:
        """Save configuration to YAML file."""
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, sort_keys=False)

    @classmethod
    def find_default_config(cls) -> Path | None:
        """Locate default config file in PROJECT_ROOT / configs / default_batch.yaml."""
        if DEFAULT_CONFIG_PATH.exists():
            return DEFAULT_CONFIG_PATH
        return None

    @classmethod
    def resolve(
        cls,
        config_input: SimulationConfig | dict[str, Any] | str | Path | None = None,
    ) -> SimulationConfig:
        """Resolve and instantiate a SimulationConfig instance from diverse input types."""
        if isinstance(config_input, SimulationConfig):
            return config_input

        if isinstance(config_input, (str, Path)):
            input_path = Path(config_input)
            if not input_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {input_path}")
            if input_path.suffix.lower() == ".json":
                return cls.from_json(input_path)
            return cls.from_yaml(input_path)

        if isinstance(config_input, dict):
            return cls.from_dict(config_input)

        if config_input is None:
            default_file = cls.find_default_config()
            if default_file and default_file.exists():
                return cls.from_yaml(default_file)
            return cls()

        raise TypeError(f"Unsupported configuration input type: {type(config_input)}")
