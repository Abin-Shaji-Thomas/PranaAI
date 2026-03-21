# PranaAI — Real-Time Emergency Triage Assistant

This project explores how **context pruning + ScaleDown compression** can reduce latency in AI systems designed for emergency response.

## Features
- Emergency classification (cardiac, trauma, disaster)
- Context pruning to remove irrelevant history
- ScaleDown API integration for token reduction
- Fast retrieval using FAISS (planned)

## Current Status
🚧 Work in progress — prototype stage

## Demo Focus
This repo demonstrates:
- Context compression using ScaleDown
- Reduced token usage before LLM reasoning

## Example Use Case
Input:
Patient with chest pain and sweating

Output:
- Possible condition: Cardiac emergency
- Recommended action: ECG, aspirin, oxygen

## Tech Stack
- Python
- FastAPI (planned)
- FAISS (planned)
- ScaleDown API

## Note
This is part of the **Gen AI for Gen Z (Intel Unnati)** project.
