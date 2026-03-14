from fastapi import FastAPI
from triage_engine import analyze_emergency

app = FastAPI(title="PranaAI - Emergency Triage Assistant")

@app.get("/")
def home():
    return {"message": "PranaAI backend running"}

@app.post("/triage")
def triage(symptoms: str):
    result = analyze_emergency(symptoms)
    return result