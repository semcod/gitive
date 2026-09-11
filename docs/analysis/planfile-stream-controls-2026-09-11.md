# Link i szybkie zamykanie lokalnych ticketów Planfile

```json
{
  "id": "planfile-stream-controls-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/43",
  "evidence": [
    "src/gitive/integrations.py",
    "src/gitive/control.js",
    "src/gitive/tests/test_integrations.py"
  ]
}
```

Lokalne zadania w zakładce `Zadania` pochodzą z Planfile projektu. Karta streamu
ma teraz link `Planfile ↗`, który otwiera szczegóły ticketu w centrum Gitive,
oraz przycisk `✓ Zamknij ticket`. Przycisk wykonuje istniejącą operację
`update-ticket` ze statusem `done`, zapisuje zmianę w lokalnym Planfile i
odświeża listę otwartych zadań. Zamknięty ticket nie jest ponownie zwracany
przez lokalny strumień.
