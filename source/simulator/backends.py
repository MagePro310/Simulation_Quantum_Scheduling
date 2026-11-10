"""Hardware simulator backend provider for IBM Quantum fake backends."""

from __future__ import annotations

from typing import Any
import qiskit_ibm_runtime.fake_provider as fake_provider


def get_fake_backend(name_or_backend: str | Any) -> Any:
    """Retrieve or instantiate an IBM fake backend.

    Args:
        name_or_backend: Backend class name string (e.g. 'FakeBelemV2', 'FakeBogotaV2',
                         'FakeManilaV2', 'FakeKyoto'), or a backend class / instance.

    Returns:
        Instantiated IBM fake backend instance.

    Raises:
        ValueError: If backend name is not recognized in qiskit_ibm_runtime.fake_provider.
    """
    if not isinstance(name_or_backend, str):
        if isinstance(name_or_backend, type):
            return name_or_backend()
        return name_or_backend

    backend_name = name_or_backend.strip()
    cls = getattr(fake_provider, backend_name, None)
    if cls is None:
        raise ValueError(
            f"Backend '{backend_name}' not found in qiskit_ibm_runtime.fake_provider. "
            f"Please verify spelling (e.g., FakeBelemV2, FakeBogotaV2, FakeManilaV2, FakeKyoto)."
        )
    return cls()


def default_rep_delay(backend: Any) -> float:
    """Return the backend's default wait between shots, in seconds (0.0 if it has none).

    IBM devices with dynamic repetition rate (all the fake backends used here) start
    each shot rep_delay after the previous shot's measurement. The configuration
    stores it in microseconds.
    """
    conf = getattr(backend, "_conf_dict", None)
    if conf is None and hasattr(backend, "configuration"):
        try:
            conf = backend.configuration().to_dict()
        except Exception:
            conf = None
    value = (conf or {}).get("default_rep_delay")
    return float(value) * 1e-6 if value is not None else 0.0
