"""Unit tests for feedback submission and community links endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_community_links(client):
    response = client.get("/feedback/community-links")
    assert response.status_code == 200
    data = response.json()
    assert "channel_url" in data
    assert "discussion_url" in data
    assert "t.me" in data["channel_url"]
    assert "t.me" in data["discussion_url"]


def test_submit_feedback_valid(client, tmp_path, monkeypatch):
    test_storage = tmp_path / "test_feedback.jsonl"
    monkeypatch.setattr("app.routes.feedback.FEEDBACK_FILE", test_storage)

    payload = {
        "category": "bug",
        "page_or_feature": "Scanner Dashboard",
        "message": "Encountered a layout issue when filtering stocks on 15m timeframe.",
        "contact_method": "user@example.com",
        "screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    }

    response = client.post("/feedback", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["id"].startswith("fb_")
    assert "message" in data

    # Verify storage
    assert test_storage.exists()
    content = test_storage.read_text(encoding="utf-8")
    assert "Scanner Dashboard" in content
    assert "user@example.com" in content


def test_submit_feedback_invalid_category(client):
    payload = {
        "category": "invalid_category",
        "page_or_feature": "Home",
        "message": "This should fail validation.",
    }
    response = client.post("/feedback", json=payload)
    assert response.status_code == 422


def test_list_feedback(client, tmp_path, monkeypatch):
    test_storage = tmp_path / "test_feedback.jsonl"
    monkeypatch.setattr("app.routes.feedback.FEEDBACK_FILE", test_storage)

    # Initially empty
    res = client.get("/feedback")
    assert res.status_code == 200
    assert res.json()["total"] == 0

    # Post an entry
    client.post(
        "/feedback",
        json={
            "category": "confusing_ui",
            "page_or_feature": "Paper Trading",
            "message": "Button label is not clear.",
        },
    )

    res = client.get("/feedback")
    assert res.status_code == 200
    assert res.json()["total"] == 1
    item = res.json()["items"][0]
    assert item["category"] == "confusing_ui"
    assert item["page_or_feature"] == "Paper Trading"
