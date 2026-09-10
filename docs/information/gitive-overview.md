# gitive: przegląd wariantów

```json
{
  "id": "gitive-overview",
  "kind": "information",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local",
  "source_revision": "main working tree based on f2300fe",
  "evidence": [
    "README.md",
    "glm53/tests/test_model.py",
    "glm53/tests/test_integration.py",
    "gpt6/tests/REPORT.md",
    "gpt6/tests_github/",
    "opus5/tests/test_model.py"
  ]
}
```

## Cel i zakres

Repozytorium zawiera trzy implementacje systemu, który przekształca ślady pracy nad kodem w kolejne, weryfikowalne zadania. Wszystkie warianty traktują Git jako źródło obserwacji lub pamięci, oddzielają propozycję LLM od walidacji programu i zapisują wynik wykonania jako wejście dla następnego cyklu.

## Warianty

`glm53` jest samodzielnym projektem Python z implementacją faktów, krytyka, rankingu, replayu oraz bezpiecznego przepływu refaktoryzacji i naprawy PR. `gpt6` prowadzi pamięć na osobnej gałęzi Git i integruje propozycje, issues, PR, weryfikację kandydata oraz CD przez GitHub CLI i API. `opus5` implementuje model amortyzowanego wnioskowania, który wyznacza napięcie między celem, stanem i tarciem CI, a potem punktuje propozycje.

Warianty nie są benchmarkiem jakości modeli językowych. Różnią się zakresem funkcji i środowiskiem wykonania, dlatego wyniki ich testów potwierdzają tylko konkretne kontrakty każdego katalogu.

## Weryfikacja

Główny cel `make test` uruchamia testy jednostkowe i integracyjne `glm53`, regresje Python/TypeScript oraz kontrakty GitHub `gpt6`, a także offline runner `opus5`. Testy offline nie wymagają klucza LLM ani konta GitHub.

`gpt6` posiada także raport z wykonania w [`gpt6/tests/REPORT.md`](../../gpt6/tests/REPORT.md). Informuje on o zakresie przeprowadzonych testów i nieweryfikowanych właściwościach; nie jest deklaracją działania na prawdziwym koncie GitHub ani porównaniem jakości LLM.
