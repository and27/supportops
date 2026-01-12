import argparse
import json
import os
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:8000")


def load_articles(path: Path) -> list[dict]:
    articles = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            articles.append(json.loads(line))
    return articles


def create_article(article: dict) -> dict:
    response = requests.post(f"{BASE_URL}/v1/kb", json=article, timeout=30)
    response.raise_for_status()
    return response.json()


def ingest_document(document_id: str, chunk_size: int, chunk_overlap: int, force: bool) -> None:
    payload = {
        "document_id": document_id,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "force": force,
    }
    response = requests.post(f"{BASE_URL}/v1/ingest", json=payload, timeout=60)
    response.raise_for_status()


def run() -> int:
    parser = argparse.ArgumentParser(description="Seed KB articles via agent API.")
    parser.add_argument(
        "--file",
        default=str(Path(__file__).with_name("articles.jsonl")),
        help="Path to JSONL fixtures file.",
    )
    parser.add_argument("--ingest", action="store_true", help="Run /v1/ingest after create.")
    parser.add_argument("--force", action="store_true", help="Force re-embed chunks.")
    parser.add_argument("--chunk-size", type=int, default=120)
    parser.add_argument("--chunk-overlap", type=int, default=20)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Fixtures file not found: {path}")
        return 1

    articles = load_articles(path)
    if not articles:
        print("No articles to seed.")
        return 1

    for article in articles:
        created = create_article(article)
        doc_id = created.get("id")
        print(f"Created: {created.get('title')} -> {doc_id}")
        if args.ingest and doc_id:
            ingest_document(doc_id, args.chunk_size, args.chunk_overlap, args.force)
            print(f"Ingested: {doc_id}")

    print("KB seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
