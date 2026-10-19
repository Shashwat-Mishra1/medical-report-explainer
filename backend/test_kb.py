import chromadb
from pathlib import Path

client = chromadb.PersistentClient(path=str(Path(__file__).parent / "kb"))
collection = client.get_collection("medical_kb")

for q in ["Why is my hemoglobin low?", "Should I worry about my sugar level?", "foods to lower cholesterol"]:
    result = collection.query(query_texts=[q], n_results=2)
    print("\nQuestion:", q)
    for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
        print("  ->", meta["test"], "|", meta["source_url"])