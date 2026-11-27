import json

import httpx
import respx

from tests.conftest import API

OFFERS = [{"id": 3749, "name": "Miaflow RO 0009"}, {"id": 3717, "name": "Miaflow RO 0008"}, {"id": 18001, "name": "X"}]


def _stream(sid, offers, campaign_id=7, schema="landings"):
    return {"id": sid, "campaign_id": campaign_id, "schema": schema, "type": "default", "position": 2, "offers": offers}


@respx.mock
def test_create_campaign_builds_two_streams(client):
    respx.get(f"{API}/offers/3749").respond(json=OFFERS[0])
    camp = respx.post(f"{API}/campaigns").respond(json={"id": 7, "name": "test", "alias": "abc"})
    streams = respx.post(f"{API}/streams").mock(
        side_effect=[httpx.Response(200, json={"id": 70}), httpx.Response(200, json={"id": 71})]
    )

    r = client.post("/api/campaigns", json={"name": " test ", "geo": "au, ro", "offer_id": 3749})
    assert r.status_code == 201, r.text

    body = json.loads(camp.calls[0].request.content)
    assert body["name"] == "test"
    assert (body["domain_id"], body["group_id"], body["traffic_source_id"]) == (1813, 10332, 836)

    geo, off = (json.loads(c.request.content) for c in streams.calls)
    assert geo["campaign_id"] == 7 and geo["schema"] == "redirect"
    assert geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU", "RO"]}]
    assert off["type"] == "default" and off["schema"] == "landings"
    assert off["offers"] == [{"offer_id": 3749, "share": 100, "state": "active"}]
    assert streams.calls[0].request.headers["Api-Key"] == "test-key"


@respx.mock
def test_create_campaign_rolls_back_when_stream_fails(client):
    respx.get(f"{API}/offers/3749").respond(json=OFFERS[0])
    respx.post(f"{API}/campaigns").respond(json={"id": 7, "name": "t"})
    respx.post(f"{API}/streams").respond(400, json={"error": "bad stream"})
    delete = respx.delete(f"{API}/campaigns/7").respond(json={})

    r = client.post("/api/campaigns", json={"name": "t", "geo": ["AU"], "offer_id": 3749})
    assert r.status_code == 400
    assert delete.called


def test_create_campaign_validates_geo(client):
    r = client.post("/api/campaigns", json={"name": "t", "geo": "ZZ", "offer_id": 1})
    assert r.status_code == 422
    assert "ZZ" in r.text


@respx.mock
def test_create_campaign_unknown_offer(client):
    respx.get(f"{API}/offers/555").respond(404, json={"error": "not found"})
    r = client.post("/api/campaigns", json={"name": "t", "geo": "AU", "offer_id": 555})
    assert r.status_code == 404


@respx.mock
def test_add_offer_rebalances_and_puts_full_list(client):
    respx.get(f"{API}/offers").respond(json=OFFERS)
    respx.get(f"{API}/streams/71").mock(
        side_effect=[
            httpx.Response(200, json=_stream(71, [{"offer_id": 3749, "share": 100, "state": "active"}])),
            httpx.Response(200, json=_stream(71, [
                {"offer_id": 3749, "share": 50, "state": "active"},
                {"offer_id": 3717, "share": 50, "state": "active"},
            ])),
        ]
    )
    put = respx.put(f"{API}/streams/71").respond(json={"id": 71})

    r = client.post("/api/campaigns/7/streams/71/offers", json={"offer_id": 3717})
    assert r.status_code == 200, r.text
    assert json.loads(put.calls[0].request.content) == {
        "offers": [
            {"offer_id": 3749, "share": 50, "state": "active"},
            {"offer_id": 3717, "share": 50, "state": "active"},
        ]
    }
    assert r.json()["active_share_total"] == 100
    assert [o["name"] for o in r.json()["offers"]] == ["Miaflow RO 0009", "Miaflow RO 0008"]


@respx.mock
def test_remove_offer_really_removes(client):
    respx.get(f"{API}/offers").respond(json=OFFERS)
    three = [{"offer_id": i, "share": s, "state": "active"} for i, s in [(3749, 34), (3717, 33), (18001, 33)]]
    respx.get(f"{API}/streams/71").mock(
        side_effect=[httpx.Response(200, json=_stream(71, three)), httpx.Response(200, json=_stream(71, []))]
    )
    put = respx.put(f"{API}/streams/71").respond(json={"id": 71})

    r = client.delete("/api/campaigns/7/streams/71/offers/3717")
    assert r.status_code == 200, r.text
    assert json.loads(put.calls[0].request.content)["offers"] == [
        {"offer_id": 3749, "share": 50, "state": "active"},
        {"offer_id": 18001, "share": 50, "state": "active"},
    ]


@respx.mock
def test_stream_of_other_campaign_is_rejected(client):
    respx.get(f"{API}/offers").respond(json=OFFERS)
    respx.get(f"{API}/streams/71").respond(json=_stream(71, [], campaign_id=999))
    r = client.post("/api/campaigns/7/streams/71/offers", json={"offer_id": 3717})
    assert r.status_code == 404


@respx.mock
def test_set_shares_requires_100(client):
    respx.get(f"{API}/streams/71").respond(
        json=_stream(71, [{"offer_id": 3749, "share": 50, "state": "active"}, {"offer_id": 3717, "share": 50, "state": "active"}])
    )
    r = client.put(
        "/api/campaigns/7/streams/71/offers",
        json={"offers": [{"offer_id": 3749, "share": 70}, {"offer_id": 3717, "share": 20}]},
    )
    assert r.status_code == 422
    assert "90" in r.text


@respx.mock
def test_keitaro_auth_error_is_reported_as_502(client):
    respx.get(f"{API}/campaigns").respond(401, json={"error": "Unauthorized"})
    r = client.get("/api/campaigns")
    assert r.status_code == 502
    assert "Unauthorized" in r.json()["detail"]
