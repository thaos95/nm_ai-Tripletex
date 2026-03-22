"""Lightweight TF-IDF RAG engine for Tripletex API knowledge retrieval.

Pure Python implementation — no external dependencies.
Pre-computed index stored in rag_index.json, built by scripts/build_rag_index.py.
"""
import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).parent / "rag_index.json"
_index_cache: Optional[Dict[str, Any]] = None


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-alphanumeric, remove short tokens."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


def _compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Term frequency: count / total tokens."""
    if not tokens:
        return {}
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: c / total for t, c in counts.items()}


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    dot = sum(vec_a.get(k, 0) * v for k, v in vec_b.items())
    mag_a = math.sqrt(sum(v * v for v in vec_a.values())) if vec_a else 0
    mag_b = math.sqrt(sum(v * v for v in vec_b.values())) if vec_b else 0
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def load_index() -> Dict[str, Any]:
    """Load and cache the pre-computed TF-IDF index."""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            _index_cache = json.load(f)
        logger.info("rag_index_loaded documents=%d", len(_index_cache.get("documents", [])))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("rag_index_load_failed path=%s error=%s", _INDEX_PATH, exc)
        _index_cache = {"documents": [], "idf": {}, "vectors": {}}
    return _index_cache


def query(text: str, top_k: int = 3, min_score: float = 0.05) -> List[Dict[str, Any]]:
    """Query the RAG index and return the top-k most relevant documents.

    Returns list of dicts with keys: id, title, content, score.
    """
    index = load_index()
    idf = index.get("idf", {})
    vectors = index.get("vectors", {})
    documents = {d["id"]: d for d in index.get("documents", [])}

    if not vectors or not idf:
        return []

    # Build query TF-IDF vector
    tokens = _tokenize(text)
    tf = _compute_tf(tokens)
    query_vec = {t: tf_val * idf.get(t, 0) for t, tf_val in tf.items() if t in idf}

    if not query_vec:
        return []

    # Score each document
    scored = []
    for doc_id, doc_vec in vectors.items():
        score = _cosine_similarity(query_vec, doc_vec)
        if score >= min_score:
            scored.append((doc_id, score))

    # Sort by score descending, take top_k
    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for doc_id, score in scored[:top_k]:
        doc = documents.get(doc_id, {})
        results.append({
            "id": doc_id,
            "title": doc.get("title", ""),
            "content": doc.get("content", ""),
            "score": round(score, 4),
        })
    return results


def query_for_error(task_type: str, error_message: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Convenience: query RAG with combined task type + error context."""
    combined = f"{task_type} {error_message}"
    return query(combined, top_k=top_k)
