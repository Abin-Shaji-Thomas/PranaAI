from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .triage_engine import analyze_emergency


class TriageRequest(BaseModel):
    symptoms: str = Field(..., min_length=5)
    patient_history: str = ""


app = FastAPI(title="PranaAI - Emergency Triage Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    frontend = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if frontend.exists():
        return FileResponse(frontend)
    return {"message": "PranaAI backend running", "hint": "Create frontend/index.html"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/triage")
def triage(payload: TriageRequest):
    try:
        return analyze_emergency(payload.symptoms, payload.patient_history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)