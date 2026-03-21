from pathlib import Path
import json
import re
import heapq
import os
import hashlib
from typing import Dict, List

import numpy as np

from .emergency_classifier import EMERGENCY_KEYWORDS


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "processed" / "retrieval_index"
MANIFEST_PATH = INDEX_DIR / "manifest.json"
DOCS_PATH = INDEX_DIR / "docs.json"
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.npy"
SUPPORTED_EXTENSIONS = ("*.txt", "*.csv", "*.json", "*.jsonl")
_DOC_CACHE: List[Dict[str, object]] = []
_EMBED_MODEL = None
_FAISS_INDEX = None
_FAISS_DOC_IDS: List[int] = []


def _embeddings_enabled() -> bool:
	return os.getenv("RETRIEVAL_ENABLE_EMBEDDINGS", "true").strip().lower() in {"1", "true", "yes", "y"}


def _current_embed_model_name() -> str:
	return os.getenv("RETRIEVAL_EMBED_MODEL", "all-MiniLM-L6-v2")


def _compute_corpus_signature() -> str:
	hasher = hashlib.sha256()
	if not DATA_DIR.exists():
		return hasher.hexdigest()

	rows: List[str] = []
	for pattern in SUPPORTED_EXTENSIONS:
		for source_file in DATA_DIR.rglob(pattern):
			if source_file.is_relative_to(INDEX_DIR):
				continue
			try:
				stat = source_file.stat()
				rel = source_file.relative_to(BASE_DIR).as_posix()
				rows.append(f"{rel}|{stat.st_size}|{stat.st_mtime_ns}")
			except Exception:
				continue

	for row in sorted(rows):
		hasher.update(row.encode("utf-8", errors="ignore"))

	return hasher.hexdigest()


def _get_embed_model():
	global _EMBED_MODEL
	if _EMBED_MODEL is not None:
		return _EMBED_MODEL

	if not _embeddings_enabled():
		return None

	try:
		from sentence_transformers import SentenceTransformer
		model_name = os.getenv("RETRIEVAL_EMBED_MODEL", "all-MiniLM-L6-v2")
		_EMBED_MODEL = SentenceTransformer(model_name)
		return _EMBED_MODEL
	except Exception:
		return None


def _normalized_embedding(text: str) -> np.ndarray | None:
	model = _get_embed_model()
	if model is None:
		return None

	try:
		vector = model.encode(text, normalize_embeddings=True)
		return np.asarray(vector, dtype=float)
	except Exception:
		return None


def _semantic_similarity(query_vector: np.ndarray | None, doc_vector: np.ndarray | None) -> float:
	if query_vector is None or doc_vector is None:
		return 0.0
	return float(np.dot(query_vector, doc_vector))


def _tokenize(text: str) -> set[str]:
	return {tok for tok in re.findall(r"[a-zA-Z]+", text.lower()) if len(tok) > 2}


def _extract_json_strings(node: object, out: List[str]) -> None:
	if isinstance(node, str):
		value = node.strip()
		if len(value) > 40:
			out.append(value)
		return
	if isinstance(node, dict):
		for key, value in node.items():
			if isinstance(value, str):
				joined = f"{key}: {value}".strip()
				if len(joined) > 40:
					out.append(joined)
			_extract_json_strings(value, out)
		return
	if isinstance(node, list):
		for item in node:
			_extract_json_strings(item, out)


def _infer_domain_from_path(source_file: Path) -> str:
	parts = {part.lower() for part in source_file.parts}
	if "disaster" in parts:
		return "disaster"
	if "medical" in parts:
		return "medical"
	return "general"


def invalidate_cache() -> None:
	global _DOC_CACHE, _FAISS_INDEX, _FAISS_DOC_IDS
	_DOC_CACHE = []
	_FAISS_INDEX = None
	_FAISS_DOC_IDS = []


def _serialize_docs(indexed_docs: List[Dict[str, object]]) -> List[Dict[str, object]]:
	serializable = []
	for doc in indexed_docs:
		tokens = doc.get("tokens", set()) if isinstance(doc.get("tokens"), set) else set()
		serializable.append(
			{
				"text": str(doc.get("text", "")),
				"domain": str(doc.get("domain", "general")),
				"text_lower": str(doc.get("text_lower", "")),
				"tokens": sorted(tokens),
			}
		)
	return serializable


def _persist_index(indexed_docs: List[Dict[str, object]], corpus_signature: str) -> None:
	try:
		INDEX_DIR.mkdir(parents=True, exist_ok=True)

		embeddings = []
		has_embeddings = True
		for doc in indexed_docs:
			embedding = doc.get("embedding")
			if not isinstance(embedding, np.ndarray):
				has_embeddings = False
				break
			embeddings.append(embedding.astype("float32"))

		if has_embeddings and embeddings:
			np.save(EMBEDDINGS_PATH, np.vstack(embeddings).astype("float32"))
		elif EMBEDDINGS_PATH.exists():
			EMBEDDINGS_PATH.unlink(missing_ok=True)

		DOCS_PATH.write_text(json.dumps(_serialize_docs(indexed_docs), ensure_ascii=False), encoding="utf-8")

		manifest = {
			"corpus_signature": corpus_signature,
			"embed_model": _current_embed_model_name(),
			"embeddings_enabled": _embeddings_enabled(),
			"doc_count": len(indexed_docs),
			"has_embeddings": bool(has_embeddings and embeddings),
		}
		MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	except Exception:
		return


def _try_load_persisted_index(corpus_signature: str) -> bool:
	global _DOC_CACHE
	if not MANIFEST_PATH.exists() or not DOCS_PATH.exists():
		return False

	try:
		manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
		if str(manifest.get("corpus_signature", "")) != corpus_signature:
			return False
		if str(manifest.get("embed_model", "")) != _current_embed_model_name():
			return False
		if bool(manifest.get("embeddings_enabled", False)) != _embeddings_enabled():
			return False

		doc_rows = json.loads(DOCS_PATH.read_text(encoding="utf-8"))
		if not isinstance(doc_rows, list) or not doc_rows:
			return False

		embedding_matrix = None
		if bool(manifest.get("has_embeddings", False)) and EMBEDDINGS_PATH.exists():
			embedding_matrix = np.load(EMBEDDINGS_PATH)
			if embedding_matrix.shape[0] != len(doc_rows):
				embedding_matrix = None

		loaded_docs: List[Dict[str, object]] = []
		for idx, row in enumerate(doc_rows):
			if not isinstance(row, dict):
				continue
			tokens_list = row.get("tokens", []) if isinstance(row.get("tokens", []), list) else []
			tokens = {str(token) for token in tokens_list}
			embedding = None
			if embedding_matrix is not None:
				embedding = np.asarray(embedding_matrix[idx], dtype=float)

			text = str(row.get("text", ""))
			loaded_docs.append(
				{
					"text": text,
					"domain": str(row.get("domain", "general")),
					"text_lower": str(row.get("text_lower", text.lower())),
					"tokens": tokens or _tokenize(text),
					"embedding": embedding,
				}
			)

		if not loaded_docs:
			return False

		_DOC_CACHE = loaded_docs
		_build_faiss_index(_DOC_CACHE)
		return True
	except Exception:
		return False


def warm_retrieval_cache() -> Dict[str, int]:
	docs = _load_documents(include_embeddings=True)
	return {
		"documents": len(docs),
		"faiss_indexed": len(_FAISS_DOC_IDS),
	}


def _build_faiss_index(indexed_docs: List[Dict[str, object]]) -> None:
	global _FAISS_INDEX, _FAISS_DOC_IDS
	_FAISS_INDEX = None
	_FAISS_DOC_IDS = []

	try:
		import faiss
	except Exception:
		return

	vectors: List[np.ndarray] = []
	doc_ids: List[int] = []
	for idx, item in enumerate(indexed_docs):
		embedding = item.get("embedding")
		if isinstance(embedding, np.ndarray):
			vectors.append(embedding.astype("float32"))
			doc_ids.append(idx)

	if not vectors:
		return

	mat = np.vstack(vectors).astype("float32")
	index = faiss.IndexFlatIP(mat.shape[1])
	index.add(mat)

	_FAISS_INDEX = index
	_FAISS_DOC_IDS = doc_ids


def _load_documents(include_embeddings: bool = True) -> List[Dict[str, object]]:
	global _DOC_CACHE
	if _DOC_CACHE:
		return _DOC_CACHE

	corpus_signature = _compute_corpus_signature()
	if _try_load_persisted_index(corpus_signature):
		return _DOC_CACHE

	docs: List[Dict[str, str]] = []
	if not DATA_DIR.exists():
		return docs

	for pattern in SUPPORTED_EXTENSIONS:
		for source_file in DATA_DIR.rglob(pattern):
			domain = _infer_domain_from_path(source_file)
			try:
				if source_file.suffix.lower() == ".txt":
					text = source_file.read_text(encoding="utf-8")
					for line in text.splitlines():
						line_text = line.strip()
						if len(line_text) > 40:
							docs.append({"text": line_text, "domain": domain})
				elif source_file.suffix.lower() == ".csv":
					text = source_file.read_text(encoding="utf-8", errors="ignore")
					for row in text.splitlines()[1:]:
						row_text = row.strip()
						if len(row_text) > 40:
							docs.append({"text": row_text, "domain": domain})
				elif source_file.suffix.lower() == ".json":
					payload = json.loads(source_file.read_text(encoding="utf-8", errors="ignore"))
					strings: List[str] = []
					_extract_json_strings(payload, strings)
					for item in strings:
						docs.append({"text": item, "domain": domain})
				elif source_file.suffix.lower() == ".jsonl":
					for line in source_file.read_text(encoding="utf-8", errors="ignore").splitlines():
						if not line.strip():
							continue
						record = json.loads(line)
						text = str(record.get("text", "")).strip()
						record_domain = str(record.get("domain", domain)).strip().lower() or domain
						if len(text) > 40:
							docs.append({"text": text, "domain": record_domain})
			except Exception:
				continue

	indexed_docs: List[Dict[str, object]] = []
	embeddings: List[np.ndarray | None] = [None] * len(docs)

	model = _get_embed_model() if include_embeddings else None
	if model is not None and docs:
		try:
			batch_size = int(os.getenv("RETRIEVAL_EMBED_BATCH_SIZE", "64"))
			vectors = model.encode(
				[item["text"] for item in docs],
				normalize_embeddings=True,
				batch_size=max(8, batch_size),
				show_progress_bar=False,
			)
			for idx, vec in enumerate(vectors):
				embeddings[idx] = np.asarray(vec, dtype=float)
		except Exception:
			embeddings = [None] * len(docs)

	for item in docs:
		idx = len(indexed_docs)
		text = str(item.get("text", ""))
		domain = str(item.get("domain", "general"))
		embedding = embeddings[idx] if idx < len(embeddings) else None
		indexed_docs.append(
			{
				"text": text,
				"domain": domain,
				"text_lower": text.lower(),
				"tokens": _tokenize(text),
				"embedding": embedding,
			}
		)

	_DOC_CACHE = indexed_docs
	if include_embeddings:
		_build_faiss_index(_DOC_CACHE)
	_persist_index(_DOC_CACHE, corpus_signature)
	return _DOC_CACHE


def _score(doc: Dict[str, object], query: str, emergency_type: str, query_embedding: np.ndarray | None = None) -> float:
	text = str(doc.get("text_lower", ""))
	query_lower = query.lower()
	query_tokens = _tokenize(query)
	text_tokens = doc.get("tokens", set()) if isinstance(doc.get("tokens"), set) else _tokenize(str(doc.get("text", "")))

	shared = query_tokens.intersection(text_tokens)
	token_overlap_score = len(shared) * 3

	phrase_bonus = 0
	for term in EMERGENCY_KEYWORDS.get(emergency_type, []):
		if term in text:
			phrase_bonus += 4
		elif _tokenize(term).issubset(text_tokens):
			phrase_bonus += 2

	type_bonus = 5 if emergency_type.replace("_", " ") in text else 0
	query_phrase_bonus = 6 if query_lower and query_lower in text else 0
	critical_bonus = 2 if any(k in text for k in ["spo2", "ecg", "bleeding", "evacuation", "contamination"]) else 0
	semantic_bonus = _semantic_similarity(query_embedding, doc.get("embedding")) * 10.0

	return token_overlap_score + phrase_bonus + type_bonus + query_phrase_bonus + critical_bonus + semantic_bonus


def retrieve_context(
	query: str,
	emergency_type: str,
	top_k: int = 4,
	domain: str = "medical",
	use_semantic: bool = True,
) -> List[str]:
	docs = _load_documents(include_embeddings=use_semantic)
	if not docs:
		return []

	query_embedding = _normalized_embedding(query) if use_semantic else None
    
	normalized_domain = (domain or "medical").lower().strip()

	faiss_candidates: List[Dict[str, object]] = []
	if use_semantic and query_embedding is not None and _FAISS_INDEX is not None and _FAISS_DOC_IDS:
		search_k = min(max(top_k * 20, 60), len(_FAISS_DOC_IDS))
		query_vec = np.asarray([query_embedding], dtype="float32")
		_, indices = _FAISS_INDEX.search(query_vec, search_k)
		for raw_idx in indices[0].tolist():
			if raw_idx < 0 or raw_idx >= len(_FAISS_DOC_IDS):
				continue
			doc_idx = _FAISS_DOC_IDS[raw_idx]
			if 0 <= doc_idx < len(docs):
				doc = docs[doc_idx]
				doc_domain = str(doc.get("domain", "general"))
				if doc_domain in {normalized_domain, "general"}:
					faiss_candidates.append(doc)

	candidates = faiss_candidates or [d for d in docs if d.get("domain", "general") in {normalized_domain, "general"}]
	if not candidates:
		candidates = docs

	query_tokens = _tokenize(query)
	emergency_terms = set()
	for term in EMERGENCY_KEYWORDS.get(emergency_type, []):
		emergency_terms.update(_tokenize(term))

	prefiltered = []
	for item in candidates:
		tokens = item.get("tokens", set()) if isinstance(item.get("tokens"), set) else set()
		if not tokens:
			prefiltered.append(item)
			continue
		if tokens.intersection(query_tokens) or tokens.intersection(emergency_terms):
			prefiltered.append(item)

	if prefiltered:
		candidates = prefiltered

	ranked = heapq.nlargest(top_k, candidates, key=lambda d: _score(d, query, emergency_type, query_embedding=query_embedding))
	chunks: List[str] = []
	for doc in ranked:
		chunks.append(str(doc.get("text", ""))[:1600])
	return chunks
