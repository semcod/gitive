---
id: task-stream-sort-tags-2026-09-11
kind: analysis
version: 1
date: 2026-09-11
owner: semcod/gitive
status: implemented-and-tested
ticket: https://github.com/semcod/gitive/issues/46
---

# Sortowanie i tagi w Centrum Zadań

Widok `tab=tasks` otrzymał sortowanie po wieku ticketu (`najnowsze`/`najstarsze`) oraz po priorytecie (`najwyższy`/`najniższy`). Priorytet jest normalizowany po stronie integracji z Planfile, GitHub i GitLab; brak etykiety oznacza `medium`.

Lista tagów jest budowana z aktualnego strumienia. Kliknięcie tagu ogranicza listę do ticketów zawierających dowolny z wybranych tagów. Wybrane sortowanie i tagi są zapisywane w URL jako `sort` i `tags`, więc odświeżenie strony zachowuje widok.

Zmiana obejmuje `src/gitive/control.js`, `src/gitive/integrations.py` i testy integracji. Weryfikacja: pełny zestaw testów Gitive oraz `node --check src/gitive/control.js`.
