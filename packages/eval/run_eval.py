import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:8000")
ALLOWED_ACTIONS = {"reply", "ask_clarifying", "create_ticket", "escalate"}
VECTOR_EVALS = os.getenv("VECTOR_EVALS", "false").lower() == "true"


def load_cases() -> list[dict]:
    cases_path = Path(__file__).resolve().parent / "cases" / "chat_cases.jsonl"
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
        response.raise_for_status()


def run() -> int:
    cases = load_cases()
    failures = 0

    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        health.raise_for_status()
    except Exception as exc:
        print(f"Health check failed: {exc}")
        return 2

    try:
        seed_kb()
    except Exception as exc:
        print(f"KB seed failed: {exc}")
        return 2

    for index, case in enumerate(cases, start=1):
        payload = case["input"]
        expected = case.get("expect", {})
        if expected.get("requires_vector") and not VECTOR_EVALS:
            print(f"[{index}] SKIP (vector evals disabled)")
            continue

        try:
            response = requests.post(
                f"{BASE_URL}/v1/chat", json=payload, timeout=10
            )
            response.raise_for_status()
        except Exception as exc:
            failures += 1
            print(f"[{index}] Request failed: {exc}")
            continue

        data = response.json()
        missing = {"conversation_id", "reply", "action", "confidence"} - data.keys()
        if missing:
            failures += 1
            print(f"[{index}] Missing fields: {missing}")
            continue

        if data["action"] not in ALLOWED_ACTIONS:
            failures += 1
            print(f"[{index}] Invalid action: {data['action']}")
            continue

        if data["action"] == "create_ticket":
            ticket_id = data.get("ticket_id")
            if not isinstance(ticket_id, str) or not ticket_id:
                failures += 1
                print(f"[{index}] Missing ticket_id for create_ticket")
                continue

        if expected.get("expect_citation") and (not expected.get("requires_vector") or VECTOR_EVALS):
            citations = data.get("citations")
            if not isinstance(citations, list) or not citations:
                failures += 1
                print(f"[{index}] Missing citations for KB response")
                continue

        confidence = data.get("confidence", -1)
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            failures += 1
            print(f"[{index}] Confidence out of range: {confidence}")
            continue

        if "action" in expected and data["action"] != expected["action"]:
            failures += 1
            print(
                f"[{index}] Expected action {expected['action']}, got {data['action']}"
            )
            continue

        print(f"[{index}] OK")

    if failures:
        print(f"Eval failed with {failures} failure(s).")
        return 1

    print("Eval passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
