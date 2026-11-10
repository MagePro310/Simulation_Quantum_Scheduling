"""Derive every simulator seed from the single configured base seed.

All sampling in a run (Aer noisy runs, SamplerV2, and the sampled fallback of the
ideal reference, which is otherwise exact) takes its seed from
`derive_seed(execution.seed, <stream>)`:

- the same config always reproduces the same samples, and
- different streams (batches, reconstructions) draw independent samples. If two
  batches ran the same circuit with the same seed, their shots would be copies of
  each other: a job split into shot shards, or running over several batches,
  would report more shots than it actually sampled.

Seeds come from numpy's SeedSequence rather than `base + batch_id`, so streams of
different base seeds never coincide: with simple addition, base 0 batch 2 and
base 1 batch 1 would share a seed, correlating repetitions run with seeds 0..R.
"""

from __future__ import annotations

import zlib

import numpy as np


def _stream_key(part: int | str) -> int:
    """Map a stream identifier to a non-negative int (strings via a stable CRC32)."""
    if isinstance(part, str):
        return zlib.crc32(part.encode("utf-8"))
    if part < 0:
        raise ValueError(f"Seed stream identifiers must be non-negative, got {part}.")
    return int(part)


def derive_seed(base_seed: int, *stream: int | str) -> int:
    """Return the simulator seed for one stream of a run.

    Args:
        base_seed: The configured `execution.seed`.
        *stream: Identifies what is being sampled, e.g. a batch id, or
            ("reconstruction", parent_name).

    Returns:
        A seed in [1, 2**32 - 1]. Never 0: qiskit-ibm-runtime's local mode silently
        ignores a seed of 0 and would sample nondeterministically.
    """
    if base_seed < 0:
        raise ValueError(f"Base seed must be non-negative, got {base_seed}.")
    entropy = [int(base_seed), *(_stream_key(part) for part in stream)]
    seed = int(np.random.SeedSequence(entropy).generate_state(1, dtype=np.uint32)[0])
    return seed or 1
