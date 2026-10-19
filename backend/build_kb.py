import json
from pathlib import Path

import chromadb

BASE = Path(__file__).parent
client = chromadb.PersistentClient(path=str(BASE / "kb"))

try:
    client.delete_collection("medical_kb")
except Exception:
    pass
collection = client.create_collection("medical_kb")

entries = []
for name in ["knowledge.json", "knowledge_extra.json"]:
    path = BASE / name
    if path.exists():
        entries += json.loads(path.read_text(encoding="utf-8"))

collection.add(
    ids=[f"kb-{i}" for i in range(len(entries))],
    documents=[f"{e['test']}: {e['text']}" for e in entries],
    metadatas=[
        {"test": e["test"], "source_name": e["source_name"], "source_url": e["source_url"]}
        for e in entries
    ],
)
print(f"Loaded {len(entries)} notes into the knowledge base.")