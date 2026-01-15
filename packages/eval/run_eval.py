import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:8000")
ALLOWED_ACTIONS = {"reply", "ask_clarifying", "create_ticket", "escalate"}
VECTOR_EVALS = os.getenv("VECTOR_EVALS", "false").lower() == "true"
THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.json"


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


def load_thresholds() -> dict[str, dict[str, float]]:
    if THRESHOLDS_PATH.exists():
        with THRESHOLDS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    return {"default": {"min_action_accuracy": 0.85, "min_citation_rate": 1.0}}


def get_category_stats(stats: dict, category: str) -> dict:
    if category not in stats:
        stats[category] = {
            "total": 0,
            "skipped": 0,
            "action_total": 0,
            "action_correct": 0,
            "citation_total": 0,
            "citation_correct": 0,
            "handoff_total": 0,
        }
    return stats[category]


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
    thresholds = load_thresholds()
    stats: dict[str, dict[str, int]] = {}

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
        payload = dict(case["input"])
        expected = case.get("expect", {})
        category = case.get("category") or "uncategorized"
        category_stats = get_category_stats(stats, category)
        requires_vector = expected.get("requires_vector")
        if requires_vector and not VECTOR_EVALS:
            category_stats["skipped"] += 1
            print(f"[{index}] SKIP (vector evals disabled)")
            continue

        expected_action = expected.get("action")
        if expected_action:
            category_stats["action_total"] += 1
        expect_citation = expected.get("expect_citation") and (
            not requires_vector or VECTOR_EVALS
        )
        if expect_citation:
            category_stats["citation_total"] += 1
        category_stats["total"] += 1
        if expected_action:
            metadata = payload.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["eval"] = {
                "expected_action": expected_action,
                "category": category,
            }
            payload["metadata"] = metadata

        error = None
        data = None
        action = None
        try:
            response = requests.post(
                f"{BASE_URL}/v1/chat", json=payload, timeout=10
            )
            response.raise_for_status()
        except Exception as exc:
            error = f"Request failed: {exc}"
        if not error:
            data = response.json()
            missing = {"conversation_id", "reply", "action", "confidence"} - data.keys()
            if missing:
                error = f"Missing fields: {missing}"
        if not error:
            action = data.get("action")
            if action not in ALLOWED_ACTIONS:
                error = f"Invalid action: {action}"
        if not error and action == "create_ticket":
            ticket_id = data.get("ticket_id")
            if not isinstance(ticket_id, str) or not ticket_id:
                error = "Missing ticket_id for create_ticket"
        if not error and expect_citation:
            citations = data.get("citations") if isinstance(data, dict) else None
            if isinstance(citations, list) and citations:
                category_stats["citation_correct"] += 1
            else:
                error = "Missing citations for KB response"
        if not error:
            confidence = data.get("confidence", -1)
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                error = f"Confidence out of range: {confidence}"
        if expected_action and action == expected_action:
            category_stats["action_correct"] += 1
        if action in {"create_ticket", "escalate"}:
            category_stats["handoff_total"] += 1
        if not error and expected_action and action != expected_action:
            error = f"Expected action {expected_action}, got {action}"
        if error:
            failures += 1
            print(f"[{index}] {error}")
        else:
            print(f"[{index}] OK")

    threshold_failures = []
    print("\nCategory summary:")
    for category, category_stats in sorted(stats.items()):
        total = category_stats["total"]
        skipped = category_stats["skipped"]
        action_total = category_stats["action_total"]
        citation_total = category_stats["citation_total"]
        if total == 0:
            continue
        action_accuracy = (
            category_stats["action_correct"] / action_total if action_total else 0.0
        )
        citation_rate = (
            category_stats["citation_correct"] / citation_total
            if citation_total
            else None
        )
        handoff_rate = category_stats["handoff_total"] / total
        print(
            f"- {category}: total={total}, skipped={skipped}, "
            f"action_acc={action_accuracy:.2f}, "
            f"citation_rate={'n/a' if citation_rate is None else f'{citation_rate:.2f}'}, "
            f"handoff_rate={handoff_rate:.2f}"
        )
        thresholds_for_category = thresholds.get(
            category, thresholds.get("default", {})
        )
        min_action_accuracy = thresholds_for_category.get("min_action_accuracy")
        if min_action_accuracy is not None and action_total:
            if action_accuracy < float(min_action_accuracy):
                threshold_failures.append(
                    f"{category}: action_accuracy {action_accuracy:.2f} < {min_action_accuracy}"
                )
        min_citation_rate = thresholds_for_category.get("min_citation_rate")
        if min_citation_rate is not None and citation_rate is not None:
            if citation_rate < float(min_citation_rate):
                threshold_failures.append(
                    f"{category}: citation_rate {citation_rate:.2f} < {min_citation_rate}"
                )
        max_handoff_rate = thresholds_for_category.get("max_handoff_rate")
        if max_handoff_rate is not None:
            if handoff_rate > float(max_handoff_rate):
                threshold_failures.append(
                    f"{category}: handoff_rate {handoff_rate:.2f} > {max_handoff_rate}"
                )

    if threshold_failures:
        print("\nThreshold failures:")
        for failure in threshold_failures:
            print(f"- {failure}")

    if failures or threshold_failures:
        total_failures = failures + len(threshold_failures)
        print(f"\nEval failed with {total_failures} failure(s).")
        return 1

    print("Eval passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
