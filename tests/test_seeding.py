"""Tests for deriving every simulator seed from the configured base seed."""

import pytest

from source.utils.seeding import derive_seed


def test_same_inputs_give_same_seed():
    assert derive_seed(42, 3) == derive_seed(42, 3)
    assert derive_seed(42, "reconstruction", "job7") == derive_seed(42, "reconstruction", "job7")


def test_streams_and_base_seeds_give_distinct_seeds():
    seeds = {derive_seed(base, batch) for base in range(20) for batch in range(1, 51)}
    assert len(seeds) == 20 * 50


def test_neighbouring_base_seeds_do_not_share_batch_seeds():
    """With base + batch_id, base 0 batch 2 equals base 1 batch 1; repetitions must not overlap."""
    assert derive_seed(0, 2) != derive_seed(1, 1)
    run_a = {derive_seed(0, b) for b in range(1, 101)}
    run_b = {derive_seed(1, b) for b in range(1, 101)}
    assert not run_a & run_b


def test_batch_and_reconstruction_streams_differ():
    assert derive_seed(5, 1) != derive_seed(5, "reconstruction", "job1")
    assert derive_seed(5, "reconstruction", "a") != derive_seed(5, "reconstruction", "b")


def test_seed_is_valid_for_every_simulator():
    for base in (0, 1, 2**31):
        for batch in range(1, 30):
            seed = derive_seed(base, batch)
            assert 1 <= seed < 2**32  # 0 would be ignored by qiskit-ibm-runtime local mode


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        derive_seed(-1, 1)
    with pytest.raises(ValueError):
        derive_seed(0, -1)
