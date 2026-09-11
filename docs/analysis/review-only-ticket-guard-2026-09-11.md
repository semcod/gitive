# Ochrona ticketów diagnostycznych przed nieautoryzowaną naprawą

```json
{
  "id": "review-only-ticket-guard-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/39",
  "evidence": [
    "src/gitive/jobs.py",
    "src/gitive/tests/test_jobs.py"
  ]
}
```

Podczas próby wykonania PLF-004 Gitive poprawnie rozpoznał repozytorium
`semcod/planfile`, ale następnie wysłał ticket do GLM53 mimo opisu
`Assessment: review_required` i jednoznacznego stwierdzenia, że zgłoszenie nie
jest autoryzacją naprawy. Pętlę zatrzymano w etapie `coding`; prywatny checkout
źródłowy pozostał bez nowego commita.

`jobs.start` odrzuca teraz takie zgłoszenia przed zmianą statusu na
`in_progress`, uruchomieniem testów, LLM lub zapisem w checkoutcie. Ticket
pozostaje `open` i wymaga osobnej decyzji użytkownika. Rozpoznawane są zarówno
`Assessment: review_required`, jak i sformułowania o braku autoryzacji naprawy.

Test regresyjny sprawdza, że zwykły ticket naprawczy nadal może być uruchomiony,
a diagnostyczny kończy się komunikatem bez utworzenia wykonania.
