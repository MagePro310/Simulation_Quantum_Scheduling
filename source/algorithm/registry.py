"""Central registry for quantum scheduling algorithms."""

from __future__ import annotations

from typing import Any, Type

_REGISTRY: dict[str, Type] = {}


def register_algorithm(name: str):
    """Decorator to register a scheduling algorithm class under exactly one name.

    Example:
        @register_algorithm("FFD")
        class FFD:
            def execute(self, scheduler_job, machines):
                ...
    """

    def decorator(cls: Type) -> Type:
        _REGISTRY[name] = cls
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

    if name_or_instance in _REGISTRY:
        return _REGISTRY[name_or_instance](**kwargs)

    raise KeyError(
        f"Unknown scheduling algorithm '{name_or_instance}'. "
        f"Available algorithms: {list_algorithms()}"
    )


def list_algorithms() -> list[str]:
    """Return the sorted registered algorithm names."""
    # Ensure heuristics are loaded
    import source.algorithm.heuristic  # noqa: F401

    return sorted(_REGISTRY)
