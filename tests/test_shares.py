import pytest

from app.services.shares import active_total, add_offer, rebalance, remove_offer


def offers(*shares, states=None):
    states = states or ["active"] * len(shares)
    return [{"offer_id": i + 1, "share": s, "state": st} for i, (s, st) in enumerate(zip(shares, states))]


@pytest.mark.parametrize(
    "n, expected",
    [(1, [100]), (2, [50, 50]), (3, [34, 33, 33]), (6, [17, 17, 17, 17, 16, 16]), (7, [15, 15, 14, 14, 14, 14, 14])],
)
def test_rebalance_even_split_remainder_goes_first(n, expected):
    result = rebalance(offers(*([0] * n)))
    assert [o["share"] for o in result] == expected
    assert active_total(result) == 100


def test_add_offer_rebalances():
    result = add_offer(offers(100), 99)
    assert [(o["offer_id"], o["share"]) for o in result] == [(1, 50), (99, 50)]


def test_remove_offer_rebalances_and_really_removes():
    result = remove_offer(offers(34, 33, 33), 2)
    assert [(o["offer_id"], o["share"]) for o in result] == [(1, 50), (3, 50)]


def test_remove_last_offer_leaves_empty_list():
    assert remove_offer(offers(100), 1) == []


def test_disabled_offers_keep_share_and_are_not_counted():
    result = add_offer(offers(60, 40, states=["active", "disabled"]), 5)
    assert [(o["offer_id"], o["share"], o["state"]) for o in result] == [
        (1, 50, "active"),
        (2, 40, "disabled"),
        (5, 50, "active"),
    ]
    assert active_total(result) == 100


def test_add_duplicate_and_remove_missing_raise():
    with pytest.raises(ValueError):
        add_offer(offers(100), 1)
    with pytest.raises(ValueError):
        remove_offer(offers(100), 42)


def test_input_not_mutated():
    src = offers(100)
    add_offer(src, 2)
    assert src == offers(100)
