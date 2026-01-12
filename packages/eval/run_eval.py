import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:8000")
ALLOWED_ACTIONS = {"reply", "ask_clarifying", "create_ticket", "escalate"}


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


def run() -> int:
    cases = load_cases()
    failures = 0

    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        health.raise_for_status()
    except Exception as exc:
        print(f"Health check failed: {exc}")
        return 2

    for index, case in enumerate(cases, start=1):
        payload = case["input"]
        expected = case.get("expect", {})

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
