# Ochrona przed wykonaniem ticketu na złym repozytorium

```json
{
  "id": "ticket-target-guard-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/27",
  "evidence": [
    "src/gitive/jobs.py",
    "src/gitive/tests/test_jobs.py"
  ]
}
```

PLF-004, PLF-005 i PLF-007 są zapisane w Planfile projektu `doctor-agent`,
ale ich treść wskazuje źródła `semcod/planfile`. Bez kontroli Gitive mógłby
uruchomić wykonawcę na checkoutcie `doctor-agent`, mimo że zadanie dotyczy
innego repozytorium.

Przed rozpoczęciem ticketu Gitive odczytuje deklarowane `Source:`,
`target_repository:` i `Repository:` oraz repozytorium projektu. Niezgodność
kończy się błędem z nazwą właściwego repozytorium. Nie wykonuje się LLM, testów
naprawy ani zapisu do checkoutu. Właściwy następny krok to zarejestrowanie
prywatnego projektu `semcod/planfile` albo utworzenie ticketu dotyczącego
`subactor/doctor-agent`.

Test regresyjny potwierdza blokadę dla `semcod/planfile` w projekcie
`subactor/doctor-agent`.
