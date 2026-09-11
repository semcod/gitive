# Autoryzacja i obsługa ticketów diagnostycznych (review_required) oraz reset pętli

```json
{
  "id": "diagnostic-review-authorization-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/42",
  "evidence": [
    "src/gitive/jobs.py",
    "src/gitive/control.py",
    "src/gitive/engine.py",
    "src/gitive/server.py",
    "src/gitive/cli.py",
    "src/gitive/control.js",
    "src/gitive/tests/test_jobs.py",
    "src/gitive/tests/test_control.py",
    "src/gitive/tests/test_engine.py",
    "src/gitive/tests/test_cli.py"
  ]
}
```

## Kontekst i problem

Wprowadzona w ticket-039 ochrona przed automatyczną naprawą zgłoszeń diagnostycznych
(`Assessment: review_required` oraz `not repair authorization`) poprawnie blokowała
wysyłanie takich zgłoszeń bezpośrednio do LLM. Brakowało jednak:

1. **Możliwości autoryzacji przez użytkownika**: Użytkownik, który świadomie zweryfikował
   zgłoszenie i chciał uruchomić naprawę, otrzymywał błąd bez żadnego przełącznika (`--authorize`).
2. **Czytelności w GUI**: Zgłoszenia diagnostyczne w panelu WWW nie były oznaczone odrębnym
   statusem ani etykietą, a przycisk „Uruchom ticket” kończył się błędem 400 Bad Request.
3. **Tworzenia powiązanego zadania naprawczego**: Zgodnie z wytycznymi w `Acceptance`
   („create a separately scoped repair with regression tests”), użytkownik powinien mieć
   możliwość jednym kliknięciem utworzyć zadanie potomne typu `[Naprawa]`.
4. **Widoczności błędów i resetowania pętli wykonawcy**: W widoku runnera błędy
   (`loop.error` / `interrupted` / `blocked`) nie były wyświetlane jako komunikat, a pętla
   pozostawała w stanie zawieszenia bez przycisku resetu do stanu gotowości (`idle`).

## Rozwiązanie

1. **Backend i ochrona (`jobs.py`, `control.py`)**:
   - Dodano parametr `authorize=False` do `jobs.start()` i `_start()`.
   - Zgłoszenia z `review_required` są odrzucane tylko wtedy, gdy `not authorize`.
   - Obiekt ticketu (`ticket_view`) zwraca pole `requires_human_review: bool`.
   - Akcja `run-ticket` oraz `realize-remote-ticket` przyjmuje `authorize: true`.

2. **CLI (`cli.py`)**:
   - Polecenie `gitive tickets run <project> [ticket] --authorize` pozwala świadomie
     autoryzować i rozpocząć procedurę naprawczą.

3. **Interfejs WWW (`control.js`)**:
   - Etykieta `Diagnostyczny (review)` na tablicy oraz w modalach.
   - W oknie szczegółów ticketu dedykowany żółty boks ostrzegawczy z dwoma przyciskami:
     - `⚡ Autoryzuj i napraw` (wywołuje `run-ticket` z `authorize: true`).
     - `+ Utwórz zadanie naprawcze` (automatycznie wstępnie wypełnia formularz tworzenia
       zadania potomnego z prefiksem `[Naprawa]` i powiązaniem nadrzędnym).
   - W widoku Runnera: wyświetlanie paska błędu/blokady z pełną treścią `loop.error`
     oraz przycisk `Wyczyść stan pętli (Gotowość) ↺` (wywołujący `/api/reset`).

4. **Metoda `Engine.reset()` i endpoint `/api/reset`**:
   - Umożliwia bezpieczne zresetowanie kontrolera do stanu `idle` po awarii lub zatrzymaniu.
