---
id: testql-stream-filter-regression-2026-09-11
kind: analysis
version: 1
date: 2026-09-11
owner: semcod/gitive
status: fixed-and-tested
ticket: https://github.com/semcod/gitive/issues/49
---

# TestQL: filtr tagów po wejściu z URL

TestQL wykazał, że wejście do widoku z `tags=planfile` traciło filtr podczas pierwszego renderu. Przyczyna: render odbywał się przed asynchronicznym pobraniem ticketów i pusty zestaw dostępnych tagów zerował wybór z URL.

Naprawa zachowuje tagi do czasu otrzymania ticketów. Dodany scenariusz `testql-scenarios/gitive-task-sort-tags-e2e.testql.toon.yaml` sprawdza sortowanie `oldest`, odtworzenie tagu `planfile`, obecność `Wyczyść tagi` i usunięcie filtra.

Wynik: scenariusz regresyjny **11/11**, pełny katalog TestQL z `--url http://127.0.0.1:8793` bez błędów.
