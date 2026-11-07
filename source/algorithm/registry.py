"""Central registry for quantum scheduling algorithms."""

from __future__ import annotations

from typing import Any, Type

_REGISTRY: dict[str, Type] = {}


def register_algorithm(*names: str):
    """Decorator to register a scheduling algorithm class under one or more names.

    Names are registered case-insensitively.

    Example:
        @register_algorithm("FFD")
        class FFD:
            def execute(self, scheduler_job, machines):
                ...
    """

    def decorator(cls: Type) -> Type:
        # Register class name automatically
        _REGISTRY[cls.__name__] = cls
        _REGISTRY[cls.__name__.lower()] = cls

        for name in names:
            clean = name.strip()
            _REGISTRY[clean] = cls
            _REGISTRY[clean.lower()] = cls
        return cls

    return decorator


def get_algorithm(name_or_instance: str | Any, **kwargs) -> Any:
    """Retrieve or instantiate an algorithm by name or instance.

    Args:
        name_or_instance: Registered algorithm name string (e.g. 'FFD', 'Adaptive_FFD',
                          'LPT', 'QGroup'), or an already instantiated algorithm object.
        **kwargs: Optional constructor arguments passed to algorithm class.

    Returns:
        Instantiated scheduling algorithm.

    Raises:
        KeyError: If algorithm name is not registered.
    """
    if not isinstance(name_or_instance, str):
        return name_or_instance

    # Ensure heuristics are loaded
    import source.algorithm.heuristic  # noqa: F401

    key = name_or_instance.strip()
    if key in _REGISTRY:
        return _REGISTRY[key](**kwargs)
    if key.lower() in _REGISTRY:
        return _REGISTRY[key.lower()](**kwargs)

    raise KeyError(
        f"Unknown scheduling algorithm '{name_or_instance}'. "
        f"Available algorithms: {list_algorithms()}"
    )


def list_algorithms() -> list[str]:
    """Return sorted unique list of primary registered algorithm names."""
    # Ensure heuristics are loaded
    import source.algorithm.heuristic  # noqa: F401

    return sorted(list({cls.__name__ for cls in _REGISTRY.values()}))
