# Ticket nie kończy się przez zielone testy bazowe

```json
{
  "id": "ticket-acceptance-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/24",
  "evidence": [
    "src/gitive/runtime_develop.py",
    "src/gitive/develop.py",
    "src/gitive/tests/test_runtime_develop.py"
  ]
}
```

## Ustalenie

`doctor-agent` ma zielony zestaw 238 testów, ale otwarte tickety PLF-004,
PLF-005 i PLF-007 zawierają dodatkową treść do wykonania. Wcześniejszy warunek
`already_green` kończył pracę przed przekazaniem tej treści wybranemu
wykonawcy.

## Poprawka

`already_green` jest teraz dozwolone tylko dla uruchomienia projektu bez
konkretnego `planfile_ticket`. Ticket Planfile zawsze przechodzi przez
propozycję wykonawcy, walidację edycji i ponowne testy runtime. Zielony baseline
jest przekazywany jako dowód, ale nie jest traktowany jako spełnienie kryterium
ticketu.

## Weryfikacja

- test regresyjny potwierdza, że zielony baseline bez ticketu kończy się
  `already_green`;
- zielony baseline z `PLF-004` nie kończy się automatycznie;
- testy `test_runtime_develop`, `test_jobs` i `test_develop`: **8/8**.
