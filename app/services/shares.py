"""Offer share ("доля") arithmetic for a Keitaro stream.

Rules (same as the Keitaro editor):
* only *active* offers take part in rotation, their shares must sum to exactly 100;
* when an offer is added or removed, active offers get an equal split, and the
  integer remainder (+1 %) goes to the first offers in the list,
  e.g. 3 offers -> 34 / 33 / 33;
* disabled offers keep whatever share they had.
"""

TOTAL = 100


def _is_active(offer: dict) -> bool:
    return offer.get("state", "active") == "active"


def rebalance(offers: list[dict]) -> list[dict]:
    active_count = sum(1 for o in offers if _is_active(o))
    if active_count == 0:
        return [dict(o) for o in offers]
    base, remainder = divmod(TOTAL, active_count)
    result = []
    for offer in offers:
        offer = dict(offer)
        if _is_active(offer):
            offer["share"] = base + (1 if remainder > 0 else 0)
            remainder -= 1
        result.append(offer)
    return result


def active_total(offers: list[dict]) -> int:
    return sum(int(o.get("share", 0)) for o in offers if _is_active(o))


def add_offer(offers: list[dict], offer_id: int) -> list[dict]:
    if any(o["offer_id"] == offer_id for o in offers):
        raise ValueError(f"Offer {offer_id} is already in the stream")
    return rebalance([*offers, {"offer_id": offer_id, "share": 0, "state": "active"}])


def remove_offer(offers: list[dict], offer_id: int) -> list[dict]:
    remaining = [o for o in offers if o["offer_id"] != offer_id]
    if len(remaining) == len(offers):
        raise ValueError(f"Offer {offer_id} is not in the stream")
    return rebalance(remaining)


def to_payload(offers: list[dict]) -> list[dict]:
    """Strip Keitaro read-only fields: PUT /streams expects offer_id/share/state only."""
    return [
        {"offer_id": int(o["offer_id"]), "share": int(o.get("share", 0)), "state": o.get("state", "active")}
        for o in offers
    ]
