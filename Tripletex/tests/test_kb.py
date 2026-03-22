"""Tests for the knowledge base and RAG system."""
from app.kb import get_forbidden_fields, get_gotchas, get_task_spec, load_kb
from app.kb.rag import query, query_for_error


class TestKnowledgeBase:
    def test_kb_loads_all_task_types(self):
        kb = load_kb()
        assert len(kb) >= 25  # At least 25 task types

    def test_supplier_invoice_forbidden_fields(self):
        forbidden = get_forbidden_fields("create_supplier_invoice")
        assert "vatType" in forbidden
        assert "vatPercentage" in forbidden

    def test_supplier_invoice_gotchas(self):
        gotchas = get_gotchas("create_supplier_invoice")
        assert len(gotchas) > 0
        # Should mention vatType
        assert any("vatType" in g for g in gotchas)

    def test_unknown_task_returns_empty(self):
        assert get_task_spec("nonexistent_task") is None
        assert get_forbidden_fields("nonexistent_task") == set()
        assert get_gotchas("nonexistent_task") == []

    def test_each_task_has_gotchas_or_forbidden(self):
        kb = load_kb()
        for task_type, spec in kb.items():
            # Every task should have at least one of: gotchas or forbidden_fields
            assert "gotchas" in spec, f"{task_type} missing gotchas key"
            assert "forbidden_fields" in spec, f"{task_type} missing forbidden_fields key"


class TestRAG:
    def test_vattype_error_retrieves_relevant_docs(self):
        results = query("supplier invoice vatType error 422")
        assert len(results) > 0
        # Top result should mention vatType
        assert any("vatType" in r["content"] for r in results)

    def test_bank_account_error_retrieves_relevant_docs(self):
        results = query("bankkontonummer invoice creation failed")
        assert len(results) > 0
        assert any("bank" in r["content"].lower() for r in results)

    def test_query_for_error_convenience(self):
        results = query_for_error("create_invoice", "bankkontonummer")
        assert len(results) > 0

    def test_empty_query_returns_empty(self):
        results = query("")
        assert results == []

    def test_irrelevant_query_has_low_scores(self):
        results = query("xyzzy foobar baz", min_score=0.3)
        assert len(results) == 0  # Nothing should match above 0.3
