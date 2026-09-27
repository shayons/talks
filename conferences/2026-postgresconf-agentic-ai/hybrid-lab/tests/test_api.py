"""The HTTP API, against the fixture database, with Bedrock mocked at the boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import unit_axis
from hybrid_lab import bedrock
from hybrid_lab.arms import ARMS, MARKER

DEFAULT_ARMS = ["keyword_or", "vector", "rrf", "rrf_rerank"]


@pytest.fixture()
def client(test_dsn, monkeypatch):
    calls = {"embed": 0, "rerank": 0}

    def fake_embed_query(text):
        calls["embed"] += 1
        return unit_axis(0)

    def fake_rerank(query, documents, top_n=None):
        calls["rerank"] += 1
        return [(index, 1.0 / (index + 1)) for index in reversed(range(len(documents)))]

    monkeypatch.setattr(bedrock, "embed_query", fake_embed_query)
    monkeypatch.setattr(bedrock, "rerank", fake_rerank)
    from hybrid_lab.server import app

    with TestClient(app) as test_client:
        test_client.calls = calls
        yield test_client


def test_lists_every_arm_and_bm25_is_available(client):
    arms = client.get("/api/arms").json()
    assert [arm["stage"] for arm in arms] == [arm.stage for arm in ARMS]
    assert all(arm["available"] for arm in arms)


def test_search_a_judged_question(client):
    response = client.post("/api/search", json={"question_id": "101", "arms": DEFAULT_ARMS})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"]["judged"] is True
    assert body["question"]["answers"] == ["3", "4", "12"]
    cards = {card["stage"]: card for card in body["arms"]}
    vector = cards["vector"]
    assert [row["doc_id"] for row in vector["rows"][:3]] == ["3", "12", "4"]
    assert vector["ndcg10"] == pytest.approx(1.0)
    assert all(row["relevant"] for row in vector["rows"][:3])
    assert cards["rrf"]["rows"][0]["vector_rank"] is not None
    rerank = cards["rrf_rerank"]
    assert rerank["source"] == "live rerank"
    assert all(row["from_rank"] for row in rerank["rows"])
    assert client.calls["rerank"] == 1


def test_union_rerank_combines_both_lists(client):
    body = client.post(
        "/api/search", json={"question_id": "101", "arms": ["vector", "bm25", "union_rerank"]}
    ).json()
    cards = {card["stage"]: card for card in body["arms"]}
    union = cards["union_rerank"]
    assert union["base_label"] == "Vector"
    vector_total, bm25_total = cards["vector"]["returned"], cards["bm25"]["returned"]
    assert max(vector_total, bm25_total) <= union["returned"] <= vector_total + bm25_total
    assert all(row["from_rank"] for row in union["rows"])  # fixture: vector ranks every post
    assert client.calls["rerank"] == 1


def test_search_typed_text_is_unjudged_and_embedded_once(client):
    body = client.post(
        "/api/search", json={"text": "safe place for savings", "arms": ["vector"]}
    ).json()
    assert body["question"]["judged"] is False
    assert body["arms"][0]["ndcg10"] is None
    assert body["arms"][0]["rows"][0]["relevant"] is None
    client.post("/api/search", json={"text": "safe place  for savings", "arms": ["vector"]})
    assert client.calls["embed"] == 1


def test_bedrock_failure_is_a_clear_503(client, monkeypatch):
    def broken(text):
        raise bedrock.BedrockError("AWS credentials are missing or expired (test).")

    monkeypatch.setattr(bedrock, "embed_query", broken)
    response = client.post("/api/search", json={"text": "brand new question", "arms": ["vector"]})
    assert response.status_code == 503
    assert "credentials" in response.json()["detail"]


def test_rejects_unknown_arms_and_questions(client):
    assert client.post("/api/search", json={"question_id": "101", "arms": ["nope"]}).status_code \
        == 400
    assert client.post("/api/search", json={"question_id": "999", "arms": ["vector"]}).status_code \
        == 404
    assert client.post("/api/search", json={"arms": ["vector"]}).status_code == 400


def test_sql_endpoint_serves_the_file_with_its_marker(client):
    source = client.get("/api/sql/rrf").json()
    assert source["file"] == "sql/08a_hybrid_rrf.sql"
    assert MARKER in source["text"]
    assert client.get("/api/sql/rrf_rerank").json()["note"]


def test_scoreboard_before_and_after_evaluation(client):
    body = client.get("/api/scoreboard")
    assert body.status_code in (200, 409)
    status = client.get("/api/status").json()
    assert status["postgres"].startswith("18")
    assert status["extensions"]["vector"].startswith("0.8")
