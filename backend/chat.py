import json
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "openai/gpt-oss-120b"
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Knowledge base built by build_kb.py. If it is missing, chat still works without it.
try:
    _kb = chromadb.PersistentClient(path=str(Path(__file__).parent / "kb")).get_collection("medical_kb")
except Exception:
    _kb = None

DISCLAIMER = "\n\n*This is general information, not medical advice. Please confirm with your doctor.*"

# Checked in code BEFORE the AI is called, so it can never be skipped
EMERGENCY_WORDS = [
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "unconscious", "seizure", "stroke", "heavy bleeding", "overdose",
    "suicide", "kill myself", "want to die",
]

EMERGENCY_REPLY = (
    "This may be an emergency. Please contact a doctor or your local emergency "
    "services right now (in India, call 112). If you are thinking of harming "
    "yourself, please reach out to someone you trust or a crisis helpline immediately."
)

SYSTEM_PROMPT = """You are a friendly assistant that helps a person understand THEIR OWN medical lab report.
Use simple words and short answers.

The person's report (statuses were computed by software, do not change them):
{data}

Trusted reference notes (use these first for general explanations):
{notes}

Rules:
- Answer ONLY from the report and the trusted notes above. Do not add facts that are in neither.
- If the answer is not there, say you don't know and suggest asking a doctor.
- Do NOT diagnose any disease. If asked "do I have X?", explain that only a doctor can diagnose, and describe what the test values show.
- Do NOT recommend medicines, supplements, or doses. Say a doctor or pharmacist must advise on that.
- Lifestyle information (food, sleep, exercise) may be given only in general terms, taken from the notes.
- For any low, high, or critical value, remind the person to discuss it with a doctor.
- If asked about something unrelated to the report or health, politely say you can only help with the report.
"""


def retrieve(question: str, tests: list[dict]) -> list[dict]:
    """Find notes for this question, plus notes for any abnormal tests in the report."""
    if _kb is None:
        return []
    found = {}

    names = sorted({t["test"] for t in tests})
    result = None
    for where in ({"test": {"$in": names}} if names else None, None):
        try:
            result = _kb.query(query_texts=[question], n_results=3, where=where)
            break
        except Exception:
            continue
    if result:
        for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
            found[doc] = meta

    abnormal = sorted({t["test"] for t in tests if t.get("status") != "normal"})
    if abnormal:
        try:
            got = _kb.get(where={"test": {"$in": abnormal}})
            for doc, meta in zip(got["documents"], got["metadatas"]):
                found[doc] = meta
        except Exception:
            pass

    return [{"text": doc, **meta} for doc, meta in list(found.items())[:5]]


def answer_question(tests: list[dict], question: str, history: list[dict]) -> dict:
    lowered = question.lower()
    if any(word in lowered for word in EMERGENCY_WORDS):
        return {"answer": EMERGENCY_REPLY, "sources": []}

    notes = retrieve(question, tests)
    notes_text = "\n\n".join(n["text"] for n in notes) or "(no reference notes available)"
    data = json.dumps(tests, indent=2, ensure_ascii=False)

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(data=data, notes=notes_text)}]
    messages += history[-6:]  # last 3 question/answer pairs
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.2)
    answer = response.choices[0].message.content.strip() + DISCLAIMER

    # Sources come from the retrieval step in code, never from the AI, so they are always real
    sources, seen = [], set()
    for n in notes:
        if n["source_url"] not in seen:
            seen.add(n["source_url"])
            sources.append({"name": n["source_name"], "url": n["source_url"]})
    return {"answer": answer, "sources": sources}