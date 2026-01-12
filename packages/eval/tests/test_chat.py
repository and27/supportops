import json
import os
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:8000")
ALLOWED_ACTIONS = {"reply", "ask_clarifying", "create_ticket", "escalate"}


def load_cases() -> list[dict]:
    cases_path = Path(__file__).resolve().parents[1] / "cases" / "chat_cases.jsonl"
    cases = []
    with cases_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def seed_kb() -> None:
    docs = [
        {
            "title": "Password reset",
            "content": "Reset the password from the login screen and verify the email.",
            "tags": ["reset"],
        },
        {
            "title": "Billing update",
            "content": "Update billing details in Settings > Billing.",
            "tags": ["billing"],
        },
    ]

    for doc in docs:
        response = requests.post(f"{BASE_URL}/v1/kb", json=doc, timeout=10)
        assert response.status_code == 201, response.text


def test_health() -> None:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True


def test_chat_cases() -> None:
    cases = load_cases()
    assert len(cases) >= 10
    seed_kb()

    for case in cases:
        payload = case["input"]
        expected = case.get("expect", {})

        response = requests.post(f"{BASE_URL}/v1/chat", json=payload, timeout=10)
        assert response.status_code == 200, response.text

        data = response.json()
        assert "conversation_id" in data
        assert "reply" in data
        assert "action" in data
        assert "confidence" in data

        assert isinstance(data["conversation_id"], str) and data["conversation_id"]
        assert isinstance(data["reply"], str) and data["reply"]
        assert data["action"] in ALLOWED_ACTIONS
        assert 0 <= data["confidence"] <= 1

        if data["action"] == "create_ticket":
            assert "ticket_id" in data
            assert isinstance(data["ticket_id"], str) and data["ticket_id"]

        if expected.get("expect_citation"):
            citations = data.get("citations")
            assert isinstance(citations, list) and citations

        if "action" in expected:
            assert data["action"] == expected["action"]
