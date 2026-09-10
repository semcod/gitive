# Odbiór shellu kontekstowego — 2026-09-10

```json
{
  "id": "context-shell-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "verified-and-deployed-local",
  "source_revision": "50093fdffa8903e83c522813f89fbcdef209cd02",
  "delivery_branch": "ticket/003-context-shell",
  "ticket": "https://github.com/semcod/gitive/issues/3",
  "evidence": ["src/gitive/tests/test_shell.py", "src/gitive/tests/test_operations.py", "src/gitive/tests/test_develop.py"]
}
```

## Wynik

Wdrożono shell `username/project/ticket/operation>` w lokalnym CLI oraz rejestr
operacji w kontenerze `loop_app-loop-1`. Projekt i ticket wybiera się z listy;
wybór trwa do `back` lub zakończenia sesji. [Instrukcja](../information/context-shell.md).

Sprawdzono działający serwer i lokalny magazyn doctor-agent: wybór PLF-001
pokazuje powiązane Issue #407 oraz `tom/doctor-agent/PLF-001/idle>`.
Trzy istniejące tickety pozostają próbami synchronizacji, a nie aktywnymi
naprawami. Nie publikowano nowych Issue ani zmian kodu doctor-agent.

## Weryfikacja

- `make test-loop` w kontenerze: **74 testy, 0 błędów, 0 pominiętych**.
- Trzy natywne adaptery wykonały planowanie, poprawki, walidację, testy i commity
  w tymczasowych repozytoriach; kontrolowane odpowiedzi SDK, bez płatnych zapytań LLM.
- Test rzeczywistego PTY: zmiana `idle` → `coding` podczas wpisywania `status`
  zachowuje częściowo wpisany tekst.
- Sprawdzono ochronę przed przypisaniem obcego projektu/ticketu, martwy PID,
  restart, uszkodzony zapis, utratę połączenia oraz przywrócenie profilera.
- SHA-256 wdrożonych modułów shell/operations/cli/develop/jobs/server odpowiada
  plikom gałęzi dostarczenia. `/health` oraz odczyt `/api/operations` działają.
- Zaktualizowano pliki głównego checkoutu dopiero po porównaniu ich z bazą PR #2;
  zachowano wcześniejszy indeks i istniejące zmiany użytkownika.

Prywatny odbiór i logi: `.subactor/recovery/context-shell/verification.json`,
`tests.log`, `build.log` w głównym checkoucie. SHA-256 logu testów:
`defb0bec0cbe6b9abf2b3803223dfa9635c9c381c805c0df77ff1d20849d6a79`.
SHA-256 logu budowania:
`f51ce6814367de995cb04dd2ec0e15f1aa50e8f798e25c7cd1da9e4abc99ffe0`.

## Ograniczenia i publikacja

Instrumentacja dotyczy adapterów uruchamianych przez Gitive development.
Nie odtwarza historycznych operacji, nie przypisuje niezależnego benchmarku do
wybranego ticketu ani nie obserwuje dowolnego procesu Codex na pulpicie.
`merge` w lokalnym adapterze opisuje fast-forward prywatnej kopii, nie merge PR.

Kontener doctor-agent z P0 wykonuje testy przez `twin test`; uruchomienie w nim
trzech wykonawców napraw pozostaje etapem P1. Shell prezentuje ten brak zgodnie
z istniejącą blokadą runtime, bez uruchamiania zastępczego Pythona aplikacji.

Zmiana jest oparta na niemergowanym PR #2 (dokładny head podany w metadanych).
Dostarczenie odbywa się osobną gałęzią i draft PR. Chroniony rejestr lokalnego
Validatora `policies/4bcf34a6aa1242bcacc2087956deccf960884ef1/direct-pr-registry.json`
nadal nie zawiera profilu `semcod/gitive`. Testy autora i wdrożenie lokalne
nie są niezależną zgodą na merge. Nie wykonano merge ani tagowania wydania.
