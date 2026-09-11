# Automatyczne trasowanie wykonania ticketu do powiązanego repozytorium projektu

```json
{
  "id": "auto-route-ticket-target-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "ticket-028",
  "evidence": [
    "src/gitive/control.py",
    "src/gitive/control.js",
    "src/gitive/jobs.py",
    "src/gitive/tests/test_control.py",
    "src/gitive/tests/test_jobs.py"
  ]
}
```

## Kontekst problemu

Gdy ticket powiązany z repozytorium (np. `semcod/planfile`) został wyświetlony lub zaimportowany pod innym projektem (np. `gitive` mającym checkout `semcod/gitive`), kliknięcie przycisku realizacji `▷ Uruchom ticket` zwracało błąd `HTTP 400`:
`Ticket wskazuje semcod/planfile; projekt ma checkout semcod/gitive. Zarejestruj właściwy projekt przed wykonaniem.`

Blokowało to realizację zadań diagnostycznych Doctora oraz zgłoszeń z GitHub Issue, mimo że właściwy projekt (`planfile`) był zarejestrowany w panelu Gitive.

## Zrealizowane zmiany

1. **Automatyczne trasowanie w backendzie (`src/gitive/control.py`)**:
   - `extract_ticket_target(title, description)` oraz `resolve_project_for_repo(projects, target_repo)` wyodrębniają docelowe repozytorium z nagłówka i opisu ticketu.
   - Operacja `run-ticket` sprawdza, czy ticket wskazuje inne repozytorium niż aktualny projekt. Jeśli docelowe repozytorium jest zarejestrowane, żądanie jest automatycznie przekierowywane do właściwego projektu (`matched_name`), a ticket jest lokalizowany lub synchronizowany w docelowym Planfile.
   - W przypadku podania identyfikatora ticketu, który fizycznie istnieje w innym zarejestrowanym projekcie, `control.py` wyszukuje go we wszystkich zarejestrowanych projektach.

2. **Automatyczne trasowanie w module zadań (`src/gitive/jobs.py`)**:
   - `_start` przechwytuje wyjątek niezgodności repozytorium (`validate_ticket_target`) i jeśli docelowe repozytorium odpowiada innemu zarejestrowanemu projektowi w rejestrze, automatycznie przełącza wykonanie na ten projekt bez przerywania operacji.

3. **Interfejs WWW (`src/gitive/control.js`)**:
   - Modal szczegółów ticketu (`ticketDetail`) wykrywa docelowe repozytorium przy użyciu `resolveTargetProject(t)`.
   - Jeśli ticket wskazuje inny zarejestrowany projekt, wyświetlany jest czytelny komunikat informacyjny:
     `ℹ️ Ten ticket dotyczy repozytorium {repo} (projekt: {matched_name}). Zostanie automatycznie zrealizowany w powiązanym projekcie {matched_name}.`
   - Etykieta przycisku realizacji dynamicznie zmienia się na `▷ Uruchom w projekcie {matched_name}`.
   - Kliknięcie przycisku realizacji wysyła zlecenie dla właściwego projektu i przełącza widok na `runner` projektu wykonującego.

4. **Weryfikacja testami**:
   - `src/gitive/tests/test_control.py`: dodano testy weryfikujące poprawne trasowanie `run-ticket` do docelowego repozytorium, lokalizację ticketu pomiędzy projektami oraz odrzucanie niezarejestrowanych repozytoriów.
   - `src/gitive/tests/test_jobs.py`: dodano test weryfikujący automatyczne przełączenie projektu w `_start`.
