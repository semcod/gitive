# Realizacja zadań z Planfile i GitHub Issue przez silniki GLM53, GPT6 i Opus5

```json
{
  "id": "planfile-task-realization-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/31",
  "evidence": [
    "src/gitive/jobs.py",
    "src/gitive/develop.py",
    "src/gitive/runtime_develop.py",
    "benchmark/adapters.py",
    "src/gitive/tests/test_develop.py"
  ]
}
```

Dotychczas wykonawcy w Gitive (GLM53, GPT6, Opus5) operowali wyłącznie na ogólnym celu projektu (`project['goal']`) i logach błędów z testów bazowych. W efekcie zadania z Planfile oraz powiązane zgłoszenia GitHub Issue nie przekazywały swojej treści, opisu ani kryteriów akceptacji do adapterów naprawczych.

W ramach biletu:
1. `src/gitive/jobs.py` przekazuje pełny kontekst ticketu (`ticket_title`, `ticket_description`, `ticket_acceptance`, `ticket_source`) do specyfikacji uruchomienia `project.json`.
2. `src/gitive/develop.py` oraz `src/gitive/runtime_develop.py` wyliczają efektywny cel z treści zadania i przekazują ustrukturyzowany pakiet dowodowy do adaptera wykonawczego. Komunikat commitu wiąże identyfikator ticketu Planfile oraz tytuł zadania.
3. `benchmark/adapters.py` dostosowuje każdy z trzech silników:
   - `GLM53`: przyjmuje zadanie ticketu jako cel natywnego mechanizmu propozycji i generowania patcha,
   - `GPT6`: omija fazę generowania losowych zadań syntetycznych i kieruje zadanie z Planfile wprost do fazy generowania poprawki z walidacją,
   - `Opus5`: aktualizuje cel wnioskowania na specyfikację ticketu i weryfikuje poprawkę w klonie.
4. Testy regresyjne i integracyjne w `src/gitive/tests/test_develop.py` potwierdzają poprawne wiązanie ticketu i generowanie zatwierdzonej poprawki.
