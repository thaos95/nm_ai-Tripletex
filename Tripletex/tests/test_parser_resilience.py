import app.parser as parser_module

from app.parser import parse_prompt
from app.schemas import ParsedTask, TaskType
from app.validator import validate_and_normalize_task


def test_parse_prompt_repairs_mojibake_before_rule_parsing(monkeypatch) -> None:
    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", lambda _prompt: None)
    parsed = parse_prompt(
        "CrÃ©ez et envoyez une facture au client Ã‰toile SARL (nÂº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse."
    )
    validated = validate_and_normalize_task(parsed)

    assert validated.parsed_task.task_type == TaskType.CREATE_INVOICE
    assert validated.parsed_task.related_entities["invoice"]["description"] == "Rapport d'analyse"


def test_parse_prompt_prefers_more_complete_rule_based_result_when_llm_is_weaker(monkeypatch) -> None:
    prompt = 'Crie o projeto "Implementação Rio" vinculado ao cliente Rio Azul Lda (org. nº 827937223). O gerente de projeto é Gonçalo Oliveira (goncalo.oliveira@example.org).'

    def fake_llm_parse(_prompt):
        return ParsedTask(
            task_type=TaskType.CREATE_PROJECT,
            confidence=0.75,
            language_hint="pt",
            fields={"name": "Implementação Rio"},
            related_entities={"customer": {"name": "Rio Azul Lda"}},
        )

    monkeypatch.setattr(parser_module, "parse_prompt_with_llm", fake_llm_parse)

    parsed = parse_prompt(prompt)

    assert parsed.task_type == TaskType.CREATE_PROJECT
    assert parsed.related_entities["customer"]["organizationNumber"] == "827937223"
    assert parsed.related_entities["project_manager"]["email"] == "goncalo.oliveira@example.org"
