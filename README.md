# nm-ai2

`nm-ai2` er et enkelt Python-prosjekt satt opp som en ren baseline for videre utvikling.

## Hva er dette prosjektet?

Et profesjonelt utgangspunkt for et Python 3.11+-prosjekt med CI, kode-skanning og Dependabot klart fra start. Enkelt å bygge videre på.

## Filstruktur

```
nm-ai2/
├── main.py              # Inngangspunkt
├── requirements.txt     # Avhengigheter
├── .gitignore
├── tests/
│   └── test_main.py     # pytest-tester
└── .github/
    ├── dependabot.yml
    ├── copilot-instructions.md
    └── workflows/
        ├── ci.yml       # Kjører tester på push/PR
        └── codeql.yml   # Kode-skanning
```

## Krav

- Python 3.11 eller nyere

## Installere avhengigheter

```bash
pip install -r requirements.txt
```

## Kjøre prosjektet

```bash
python main.py
```

## Kjøre tester

```bash
pytest
```

## Neste steg

- Legg til forretningslogikk i `main.py` eller nye moduler
- Utvid testene i `tests/`
- Legg til nye avhengigheter i `requirements.txt` ved behov
