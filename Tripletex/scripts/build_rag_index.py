#!/usr/bin/env python3
"""Build the TF-IDF RAG index from KB docs and gotchas.

Usage:
    cd Tripletex
    python scripts/build_rag_index.py

Reads:
    app/kb/docs/*.md          — endpoint and error pattern documents
    app/kb/task_registry.json — gotchas per task type

Writes:
    app/kb/rag_index.json     — pre-computed TF-IDF index
"""
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List

KB_DIR = Path(__file__).parent.parent / "app" / "kb"
DOCS_DIR = KB_DIR / "docs"
REGISTRY_PATH = KB_DIR / "task_registry.json"
OUTPUT_PATH = KB_DIR / "rag_index.json"


def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


def extract_documents_from_markdown(filepath: Path) -> List[Dict[str, Any]]:
    """Split a markdown file into documents by ## headings."""
    docs = []
    text = filepath.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    stem = filepath.stem
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        title = lines[0].strip().lstrip("# ")
        content = lines[1].strip() if len(lines) > 1 else title
        doc_id = f"{stem}_{i}" if i > 0 else f"{stem}_header"
        docs.append({
            "id": doc_id,
            "title": title,
            "content": f"{title}. {content}",
            "source": str(filepath.name),
        })
    return docs


def extract_gotcha_documents(registry_path: Path) -> List[Dict[str, Any]]:
    """Extract gotchas from task_registry.json as individual documents."""
    docs = []
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    for task_type, spec in registry.items():
        gotchas = spec.get("gotchas", [])
        for j, gotcha in enumerate(gotchas):
            doc_id = f"gotcha_{task_type}_{j}"
            docs.append({
                "id": doc_id,
                "title": f"{task_type}: {gotcha[:60]}",
                "content": f"Task type {task_type}. {gotcha}",
                "source": "task_registry.json",
            })
    return docs


def compute_idf(all_docs: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute inverse document frequency for all terms."""
    n_docs = len(all_docs)
    doc_freq: Dict[str, int] = {}
    for doc in all_docs:
        tokens = set(tokenize(doc["content"]))
        for t in tokens:
            doc_freq[t] = doc_freq.get(t, 0) + 1
    return {t: math.log(n_docs / df) for t, df in doc_freq.items() if df < n_docs}


def compute_tfidf_vector(text: str, idf: Dict[str, float]) -> Dict[str, float]:
    """Compute TF-IDF vector for a document."""
    tokens = tokenize(text)
    if not tokens:
        return {}
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: (c / total) * idf.get(t, 0) for t, c in counts.items() if t in idf}


def main():
    # Collect all documents
    all_docs: List[Dict[str, Any]] = []

    # From markdown files
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        docs = extract_documents_from_markdown(md_file)
        all_docs.extend(docs)
        print(f"  {md_file.name}: {len(docs)} documents")

    # From KB gotchas
    if REGISTRY_PATH.exists():
        gotcha_docs = extract_gotcha_documents(REGISTRY_PATH)
        all_docs.extend(gotcha_docs)
        print(f"  task_registry.json gotchas: {len(gotcha_docs)} documents")

    print(f"\nTotal documents: {len(all_docs)}")

    # Compute IDF
    idf = compute_idf(all_docs)
    print(f"Vocabulary size: {len(idf)} terms")

    # Compute per-document TF-IDF vectors
    vectors: Dict[str, Dict[str, float]] = {}
    for doc in all_docs:
        vec = compute_tfidf_vector(doc["content"], idf)
        if vec:
            vectors[doc["id"]] = vec

    # Build the index
    index = {
        "idf": {k: round(v, 4) for k, v in idf.items()},
        "documents": all_docs,
        "vectors": {doc_id: {k: round(v, 4) for k, v in vec.items()} for doc_id, vec in vectors.items()},
    }

    # Write
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    file_size = OUTPUT_PATH.stat().st_size
    print(f"\nWrote {OUTPUT_PATH} ({file_size:,} bytes)")
    print(f"Documents: {len(all_docs)}, Vectors: {len(vectors)}, Terms: {len(idf)}")


if __name__ == "__main__":
    main()
