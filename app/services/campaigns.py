"""Business logic: campaign creator and offer editor on top of the Keitaro API."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign, Operation
from app.services import shares

log = logging.getLogger(__name__)


class ServiceError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# ---------------------------------------------------------------- offers cache

_OFFERS_TTL = 300.0
_offers_cache: tuple[float, list[dict]] | None = None


async def get_offers(kt: KeitaroClient, force: bool = False) -> list[dict]:
    global _offers_cache
    now = time.monotonic()
    if not force and _offers_cache and now - _offers_cache[0] < _OFFERS_TTL:
        return _offers_cache[1]
    offers = await kt.list_offers()
    _offers_cache = (now, offers)
    return offers


def reset_offers_cache() -> None:
    global _offers_cache
    _offers_cache = None


async def offer_names(kt: KeitaroClient) -> dict[int, str]:
    return {int(o["id"]): o.get("name", "") for o in await get_offers(kt)}


async def search_offers(kt: KeitaroClient, q: str, limit: int = 30) -> list[dict]:
    q = q.strip().lower()
    result = []
    for o in await get_offers(kt):
        haystack = f"{o['id']} {o.get('name', '')}".lower()
        if not q or q in haystack:
            result.append({"id": o["id"], "name": o.get("name", ""), "state": o.get("state")})
        if len(result) >= limit:
            break
    return result


def _log(db: Session, keitaro_campaign_id: int, action: str, details: dict) -> None:
    local = db.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_campaign_id))
    db.add(
        Operation(
            keitaro_campaign_id=keitaro_campaign_id,
            campaign_id=local.id if local else None,
            action=action,
            details=details,
        )
    )


# ------------------------------------------------------------ campaign creator

async def create_campaign(
    db: Session, kt: KeitaroClient, settings: Settings, name: str, geo: list[str], offer_id: int
) -> dict:
    # 1. the offer must exist, otherwise we'd create a campaign that points nowhere
    try:
        offer = await kt.get_offer(offer_id)
    except KeitaroError as exc:
        if exc.status_code == 404:
            raise ServiceError(404, f"Offer {offer_id} not found in Keitaro") from exc
        raise

    # 2. campaign with domain, group and traffic source
    campaign = await kt.create_campaign(
        {
            "name": name,
            "type": "position",
            "state": "active",
            "cost_type": "CPC",
            "cost_value": 0,
            "cost_currency": "USD",
            "domain_id": settings.keitaro_domain_id,
            "group_id": settings.keitaro_group_id,
            "traffic_source_id": settings.keitaro_traffic_source_id,
        }
    )
    campaign_id = int(campaign["id"])

    # 3. two streams; if either fails, remove the half-built campaign
    try:
        geo_stream = await kt.create_stream(
            {
                "campaign_id": campaign_id,
                "name": f"Geo {', '.join(geo)} → Google",
                "type": "regular",
                "position": 1,
                "state": "active",
                "schema": "redirect",
                "action_type": "http",
                "action_payload": settings.geo_redirect_url,
                "filters": [{"name": "country", "mode": "accept", "payload": geo}],
            }
        )
        offers_stream = await kt.create_stream(
            {
                "campaign_id": campaign_id,
                "name": "Offers",
                "type": "default",
                "position": 2,
                "state": "active",
                "schema": "landings",
                "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
            }
        )
    except KeitaroError:
        log.exception("Stream creation failed, rolling back campaign %s", campaign_id)
        try:
            await kt.delete_campaign(campaign_id)
        except KeitaroError:
            log.exception("Rollback of campaign %s failed", campaign_id)
        raise

    local = Campaign(
        keitaro_id=campaign_id,
        name=campaign.get("name", name),
        alias=campaign.get("alias"),
        geo=geo,
        geo_stream_id=geo_stream.get("id"),
        offers_stream_id=offers_stream.get("id"),
    )
    db.add(local)
    db.flush()
    db.add(
        Operation(
            keitaro_campaign_id=campaign_id,
            campaign_id=local.id,
            action="create_campaign",
            details={"name": name, "geo": geo, "offer_id": offer_id, "offer_name": offer.get("name")},
        )
    )
    db.commit()

    return {
        "campaign": campaign,
        "streams": [geo_stream, offers_stream],
        "admin_url": f"{settings.keitaro_url.rstrip('/')}/admin/#!/campaign.editor/{campaign_id}",
    }


# -------------------------------------------------------------- offer editor

async def list_campaigns(db: Session, kt: KeitaroClient) -> list[dict]:
    remote = await kt.list_campaigns()
    local_ids = set(db.scalars(select(Campaign.keitaro_id)))
    return [
        {
            "id": c["id"],
            "name": c.get("name"),
            "alias": c.get("alias"),
            "state": c.get("state"),
            "created_here": int(c["id"]) in local_ids,
        }
        for c in sorted(remote, key=lambda c: -int(c["id"]))
    ]


def _decorate_stream(stream: dict, names: dict[int, str]) -> dict:
    offers = [
        {
            "offer_id": int(o["offer_id"]),
            "name": names.get(int(o["offer_id"]), f"Offer #{o['offer_id']}"),
            "share": int(o.get("share", 0)),
            "state": o.get("state", "active"),
        }
        for o in stream.get("offers") or []
    ]
    return {**stream, "offers": offers, "active_share_total": shares.active_total(offers)}


async def get_campaign_details(db: Session, kt: KeitaroClient, campaign_id: int) -> dict:
    campaign = await kt.get_campaign(campaign_id)
    streams = await kt.list_streams(campaign_id)
    names = await offer_names(kt)
    streams = sorted(streams, key=lambda s: s.get("position") or 0)
    ops = db.scalars(
        select(Operation)
        .where(Operation.keitaro_campaign_id == campaign_id)
        .order_by(Operation.id.desc())
        .limit(50)
    ).all()
    return {
        "campaign": campaign,
        "streams": [_decorate_stream(s, names) for s in streams],
        "operations": [
            {"id": o.id, "action": o.action, "details": o.details, "created_at": o.created_at.isoformat()}
            for o in ops
        ],
    }


async def _load_landings_stream(kt: KeitaroClient, campaign_id: int, stream_id: int) -> dict:
    stream = await kt.get_stream(stream_id)
    if int(stream.get("campaign_id", 0)) != campaign_id:
        raise ServiceError(404, f"Stream {stream_id} does not belong to campaign {campaign_id}")
    if stream.get("schema") != "landings":
        raise ServiceError(400, f"Stream {stream_id} does not hold offers (schema={stream.get('schema')})")
    return stream


async def _save_offers(
    db: Session, kt: KeitaroClient, campaign_id: int, stream: dict, new_offers: list[dict], action: str, extra: dict
) -> dict:
    before = shares.to_payload(stream.get("offers") or [])
    after = shares.to_payload(new_offers)
    # PUT /streams/{id}: the "offers" field replaces the whole offer list
    await kt.update_stream(int(stream["id"]), {"offers": after})
    # read back what Keitaro actually stored, so the UI shows the real numbers
    saved = await kt.get_stream(int(stream["id"]))
    _log(db, campaign_id, action, {"stream_id": stream["id"], **extra, "before": before, "after": after})
    db.commit()
    return _decorate_stream(saved, await offer_names(kt))


async def add_offer(db: Session, kt: KeitaroClient, campaign_id: int, stream_id: int, offer_id: int) -> dict:
    names = await offer_names(kt)
    if offer_id not in names:
        raise ServiceError(404, f"Offer {offer_id} not found in Keitaro")
    stream = await _load_landings_stream(kt, campaign_id, stream_id)
    try:
        new_offers = shares.add_offer(shares.to_payload(stream.get("offers") or []), offer_id)
    except ValueError as exc:
        raise ServiceError(409, str(exc)) from exc
    return await _save_offers(db, kt, campaign_id, stream, new_offers, "add_offer", {"offer_id": offer_id})


async def remove_offer(db: Session, kt: KeitaroClient, campaign_id: int, stream_id: int, offer_id: int) -> dict:
    stream = await _load_landings_stream(kt, campaign_id, stream_id)
    try:
        new_offers = shares.remove_offer(shares.to_payload(stream.get("offers") or []), offer_id)
    except ValueError as exc:
        raise ServiceError(404, str(exc)) from exc
    return await _save_offers(db, kt, campaign_id, stream, new_offers, "remove_offer", {"offer_id": offer_id})


async def set_shares(
    db: Session, kt: KeitaroClient, campaign_id: int, stream_id: int, offers: list[dict]
) -> dict:
    stream = await _load_landings_stream(kt, campaign_id, stream_id)
    current = {int(o["offer_id"]) for o in stream.get("offers") or []}
    incoming = [int(o["offer_id"]) for o in offers]
    if len(set(incoming)) != len(incoming) or set(incoming) != current:
        raise ServiceError(409, "Offer list changed — reload the campaign and try again")
    if any(o["state"] == "active" for o in offers) and shares.active_total(offers) != shares.TOTAL:
        raise ServiceError(422, f"Shares of active offers must sum to 100, got {shares.active_total(offers)}")
    return await _save_offers(db, kt, campaign_id, stream, offers, "set_shares", {})
