import pytest

from app.attachments.service import summarize_attachment_hints


DATASETS = [
    ("912345670", "ola.hansen@example.org", "2026-03-20", "12500"),
    ("923456781", "kari.lie@example.org", "2026-04-11", "16400"),
    ("934567892", "arne.berge@example.org", "2026-05-02", "18750"),
    ("945678903", "nora.dahl@example.org", "2026-06-13", "9800"),
    ("956789014", "mina.larsen@example.org", "2026-07-24", "24300"),
    ("967890125", "even.moen@example.org", "2026-08-05", "18850"),
    ("978901236", "sara.berg@example.org", "2026-09-16", "11200"),
    ("989012347", "jonas.haugen@example.org", "2026-10-07", "15150"),
    ("990123458", "jules.martin@example.org", "2026-11-18", "13490"),
    ("901234569", "lucy.taylor@example.org", "2026-12-09", "17600"),
]


CASES = []
for index, (org, email, day, amount) in enumerate(DATASETS, start=1):
    CASES.extend(
        [
            (f"org-{index}", f"Kunde orgnr {org}", f"organization_numbers={org}"),
            (f"email-{index}", f"Kontakt {email}", f"emails={email}"),
            (f"date-{index}", f"Dato {day}", f"dates={day}"),
            (f"amount-{index}", f"Belop {amount} NOK", f"amounts={amount}"),
            (
                f"combined-{index}",
                f"Kunde {org} kontakt {email} dato {day} belop {amount} NOK",
                f"organization_numbers={org}",
            ),
            (
                f"combined-email-{index}",
                f"Kunde {org} kontakt {email} dato {day} belop {amount} NOK",
                f"emails={email}",
            ),
            (
                f"combined-date-{index}",
                f"Kunde {org} kontakt {email} dato {day} belop {amount} NOK",
                f"dates={day}",
            ),
            (
                f"combined-amount-{index}",
                f"Kunde {org} kontakt {email} dato {day} belop {amount} NOK",
                f"amounts={amount}",
            ),
        ]
    )


@pytest.mark.parametrize("case_id,text,expected_fragment", CASES, ids=[case[0] for case in CASES])
def test_large_attachment_hint_matrix(case_id: str, text: str, expected_fragment: str) -> None:
    hints = summarize_attachment_hints(text)

    assert expected_fragment in hints, case_id
