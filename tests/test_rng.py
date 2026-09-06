"""Seeded random streams: the property everything else in the engine rests on.

If these break, golden replay tests break, saves stop reproducing, and a second
implementation of the engine can no longer be checked against this one.
"""

import pytest

from mace.engine.rng import Pcg64, RandomSource, derive_seed

#: PCG64 output for `pcg64_srandom_r(&rng, 42, 54)`, verified bit-for-bit
#: against numpy's `np.random.PCG64.random_raw` at the same state and
#: increment. Pinned here so a change to the generator has to be deliberate:
#: every golden replay file in this repository depends on these numbers.
REFERENCE_DRAWS = [
    9705778491962043240,
    1370407407632858425,
    11774395822783136600,
    17944889938176486912,
    14437308781460811564,
    6944869453235589526,
]


def test_pcg64_matches_the_reference_implementation() -> None:
    generator = Pcg64.seeded(42, 54)
    assert [generator.next_uint64() for _ in REFERENCE_DRAWS] == REFERENCE_DRAWS


def test_a_stream_is_reproducible_from_its_seed() -> None:
    first = RandomSource("a-seed").stream("weather")
    second = RandomSource("a-seed").stream("weather")
    assert [first.uint64() for _ in range(20)] == [second.uint64() for _ in range(20)]


def test_a_different_seed_is_a_different_world() -> None:
    first = RandomSource("one").stream("weather")
    second = RandomSource("two").stream("weather")
    assert [first.uint64() for _ in range(8)] != [second.uint64() for _ in range(8)]


def test_streams_do_not_disturb_each_other() -> None:
    """The reason streams exist at all: a long fight must not move the weather."""
    undisturbed = RandomSource("seed")
    expected = [undisturbed.stream("weather").uint64() for _ in range(5)]

    disturbed = RandomSource("seed")
    for _ in range(500):
        disturbed.stream("combat.troll-1").uint64()
    actual = [disturbed.stream("weather").uint64() for _ in range(5)]

    assert actual == expected


def test_asking_twice_continues_one_stream() -> None:
    source = RandomSource("seed")
    first = source.stream("loot").uint64()
    second = source.stream("loot").uint64()
    assert first != second
    assert source.stream("loot").position == 2


def test_stream_names_are_independent_even_when_similar() -> None:
    source = RandomSource("seed")
    near = [source.stream(f"encounters.road-{index}").uint64() for index in range(4)]
    assert len(set(near)) == 4


def test_derive_seed_is_stable_across_processes() -> None:
    """Not Python's `hash`, which is salted per process."""
    assert derive_seed("seed", "weather") == derive_seed("seed", "weather")
    assert derive_seed("seed", "weather") != derive_seed("seed", "weather.fronts")


# ── Drawing ───────────────────────────────────────────────────────────────────


def test_fractions_stay_in_range() -> None:
    stream = RandomSource("seed").stream("s")
    values = [stream.fraction() for _ in range(2000)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert 0.45 < sum(values) / len(values) < 0.55


def test_below_covers_its_range_evenly() -> None:
    stream = RandomSource("seed").stream("s")
    counts = [0] * 6
    for _ in range(60_000):
        counts[stream.below(6)] += 1
    assert all(9_000 < count < 11_000 for count in counts), counts


def test_below_rejects_an_empty_range() -> None:
    stream = RandomSource("seed").stream("s")
    with pytest.raises(ValueError, match="must be positive"):
        stream.below(0)


def test_between_includes_both_ends() -> None:
    stream = RandomSource("seed").stream("s")
    seen = {stream.between(1, 3) for _ in range(200)}
    assert seen == {1, 2, 3}


def test_certain_and_impossible_chances_draw_nothing() -> None:
    """A content mistake should not shift the stream for everything after it."""
    stream = RandomSource("seed").stream("s")
    assert stream.chance(1.0) is True
    assert stream.chance(0.0) is False
    assert stream.position == 0


def test_chance_is_roughly_its_probability() -> None:
    stream = RandomSource("seed").stream("s")
    hits = sum(stream.chance(0.25) for _ in range(10_000))
    assert 2_300 < hits < 2_700


def test_weighted_choice_follows_the_weights() -> None:
    stream = RandomSource("seed").stream("s")
    options = [("common", 90.0), ("rare", 10.0)]
    draws = [stream.weighted(options) for _ in range(10_000)]
    assert 8_800 < draws.count("common") < 9_200


def test_a_zero_weight_entry_is_disabled_not_an_error() -> None:
    stream = RandomSource("seed").stream("s")
    options = [("on", 1.0), ("off", 0.0)]
    assert {stream.weighted(options) for _ in range(50)} == {"on"}


def test_weighted_needs_something_to_choose() -> None:
    stream = RandomSource("seed").stream("s")
    with pytest.raises(ValueError, match="positive weight"):
        stream.weighted([("nothing", 0.0)])


def test_choice_needs_something_to_choose() -> None:
    stream = RandomSource("seed").stream("s")
    with pytest.raises(ValueError, match="nothing to choose"):
        stream.choice([])


def test_shuffling_keeps_every_item() -> None:
    stream = RandomSource("seed").stream("s")
    items = list(range(20))
    shuffled = stream.shuffled(items)
    assert sorted(shuffled) == items
    assert shuffled != items
    assert items == list(range(20)), "the input is left alone"


# ── Saving and resuming ───────────────────────────────────────────────────────


def test_a_restored_source_carries_on_mid_sequence() -> None:
    source = RandomSource("seed")
    for _ in range(7):
        source.stream("weather").uint64()
    for _ in range(3):
        source.stream("loot").uint64()

    resumed = RandomSource.restore("seed", source.snapshot())
    assert resumed.positions() == source.positions()
    assert resumed.stream("weather").uint64() == source.stream("weather").uint64()
    assert resumed.stream("loot").uint64() == source.stream("loot").uint64()


def test_a_snapshot_does_not_depend_on_the_order_streams_were_used() -> None:
    first = RandomSource("seed")
    first.stream("weather").uint64()
    first.stream("loot").uint64()

    second = RandomSource("seed")
    second.stream("loot").uint64()
    second.stream("weather").uint64()

    assert first.snapshot() == second.snapshot()


def test_an_unused_source_snapshots_to_nothing() -> None:
    assert RandomSource("seed").snapshot() == ()
