from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_documents() -> List[str]:
	docs: List[str] = []
	if not DATA_DIR.exists():
		return docs
	for text_file in DATA_DIR.rglob("*.txt"):
		try:
			docs.append(text_file.read_text(encoding="utf-8"))
		except Exception:
			continue
	return docs


def _score(doc: str, query: str, emergency_type: str) -> int:
	q_terms = [term.strip().lower() for term in query.split() if term.strip()]
	text = doc.lower()
	term_hits = sum(1 for t in q_terms if t in text)
	type_bonus = 3 if emergency_type.replace("_", " ") in text else 0
	return term_hits + type_bonus


def retrieve_context(query: str, emergency_type: str, top_k: int = 4) -> List[str]:
	docs = _load_documents()
	if not docs:
		return []

	ranked = sorted(docs, key=lambda d: _score(d, query, emergency_type), reverse=True)
	chunks: List[str] = []
	for doc in ranked[:top_k]:
		chunks.append(doc[:1600])
	return chunks
