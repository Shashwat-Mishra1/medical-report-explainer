import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import storage
from chat import answer_question
from explainer import explain_tests
from extractor import extract_text
from parser import get_status, parse_report


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    storage.purge_old()  # privacy: delete reports (and files) older than 24 hours
    yield


app = FastAPI(title="MedReport Explainer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024


class ChatRequest(BaseModel):
    report_id: str
    question: str


class TestIn(BaseModel):
    test: str
    value: float
    unit: str = ""
    ref_low: float | None = None
    ref_high: float | None = None


class ConfirmRequest(BaseModel):
    tests: list[TestIn]


def load_report(report_id: str) -> dict:
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "MedReport Explainer API is running"}


@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, PNG, JPG and JPEG files are allowed.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File is too large (max 10 MB).")

    storage.purge_old()

    report_id = uuid.uuid4().hex
    saved_path = UPLOAD_DIR / f"{report_id}{ext}"
    saved_path.write_bytes(content)

    try:
        result = extract_text(str(saved_path))
    except Exception as e:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not read the file: {e}")

    if len(result["text"]) < 20:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No readable text found. Please upload a clearer file.")

    tests = parse_report(result["text"])

    # The raw text is not stored: it can contain the patient's name and phone number
    storage.create_report(report_id, str(saved_path), "parsed", result["method"], tests)
    return {
        "report_id": report_id,
        "status": "parsed",
        "extraction_method": result["method"],
        "tests_found": len(tests),
        "tests": tests,
    }


@app.get("/report/{report_id}")
def get_report(report_id: str):
    report = load_report(report_id)
    report.pop("file_path", None)
    return {"report_id": report_id, **report}


@app.post("/confirm/{report_id}")
def confirm_report(report_id: str, request: ConfirmRequest):
    load_report(report_id)
    if not request.tests:
        raise HTTPException(status_code=422, detail="No tests to explain.")

    # Flags are always recomputed in code, never taken from the browser or the AI
    tests = []
    for t in request.tests:
        item = t.model_dump()
        item["status"] = get_status(t.value, t.ref_low, t.ref_high)
        tests.append(item)

    try:
        explanation = explain_tests(tests)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI explanation failed: {e}")

    storage.update_report(report_id, tests=tests, explanation=explanation, status="explained")
    return {"tests": tests, "explanation": explanation}


@app.post("/explain/{report_id}")
def explain_report(report_id: str):
    report = load_report(report_id)
    if not report["tests"]:
        raise HTTPException(status_code=422, detail="No tests were found in this report.")
    try:
        explanation = explain_tests(report["tests"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI explanation failed: {e}")
    storage.update_report(report_id, explanation=explanation, status="explained")
    return explanation


@app.post("/chat")
def chat(request: ChatRequest):
    report = load_report(request.report_id)
    if not report["tests"]:
        raise HTTPException(status_code=422, detail="No tests were found in this report.")
    try:
        result = answer_question(report["tests"], request.question, report["chat"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI answer failed: {e}")
    history = report["chat"] + [
        {"role": "user", "content": request.question},
        {"role": "assistant", "content": result["answer"]},
    ]
    storage.update_report(request.report_id, chat=history)
    return result


@app.delete("/report/{report_id}")
def delete_report(report_id: str):
    file_path = storage.delete_report(report_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    if file_path:
        Path(file_path).unlink(missing_ok=True)
    return {"deleted": True}