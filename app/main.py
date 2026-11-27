from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.countries import COUNTRY_CODES
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError, close_keitaro, get_keitaro
from app.schemas import CampaignCreate, OfferIn, SharesUpdate
from app.services import campaigns as svc

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_keitaro()


app = FastAPI(title="Keitaro wrapper", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(KeitaroError)
async def _keitaro_error(_: Request, exc: KeitaroError):
    # 401/403 from Keitaro = misconfigured key: show it as a gateway problem, not as our auth
    status = 502 if exc.status_code in (401, 403) or exc.status_code >= 500 else exc.status_code
    return JSONResponse(status_code=status, content={"detail": exc.message})


@app.exception_handler(svc.ServiceError)
async def _service_error(_: Request, exc: svc.ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/settings")
async def public_settings(
    settings: Settings = Depends(get_settings), kt: KeitaroClient = Depends(get_keitaro)
):
    """Domain / group / traffic source that every new campaign gets, with their Keitaro names."""

    def pick(rows: list[dict], wanted: int) -> dict:
        row = next((r for r in rows if int(r.get("id", 0)) == wanted), None)
        return {"id": wanted, "name": (row or {}).get("name"), "found": row is not None}

    return {
        "keitaro_url": settings.keitaro_url,
        "geo_redirect_url": settings.geo_redirect_url,
        "domain": pick(await kt.list_domains(), settings.keitaro_domain_id),
        "group": pick(await kt.list_groups(), settings.keitaro_group_id),
        "traffic_source": pick(await kt.list_traffic_sources(), settings.keitaro_traffic_source_id),
    }


@app.get("/api/countries")
async def countries():
    return sorted(COUNTRY_CODES)


@app.get("/api/offers")
async def offers(q: str = "", limit: int = 30, kt: KeitaroClient = Depends(get_keitaro)):
    return await svc.search_offers(kt, q, min(max(limit, 1), 200))


@app.get("/api/campaigns")
async def list_campaigns(db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    return await svc.list_campaigns(db, kt)


@app.post("/api/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(get_keitaro),
    settings: Settings = Depends(get_settings),
):
    return await svc.create_campaign(db, kt, settings, body.name, body.geo, body.offer_id)


@app.get("/api/campaigns/{campaign_id}")
async def campaign_details(
    campaign_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)
):
    return await svc.get_campaign_details(db, kt, campaign_id)


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}/offers")
async def add_offer(
    campaign_id: int,
    stream_id: int,
    body: OfferIn,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(get_keitaro),
):
    return await svc.add_offer(db, kt, campaign_id, stream_id, body.offer_id)


@app.delete("/api/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}")
async def remove_offer(
    campaign_id: int,
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(get_keitaro),
):
    return await svc.remove_offer(db, kt, campaign_id, stream_id, offer_id)


@app.put("/api/campaigns/{campaign_id}/streams/{stream_id}/offers")
async def set_shares(
    campaign_id: int,
    stream_id: int,
    body: SharesUpdate,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(get_keitaro),
):
    return await svc.set_shares(db, kt, campaign_id, stream_id, [o.model_dump() for o in body.offers])
