# Benchmark napraw — 20260910T122228Z-3e2b37

```json
{
  "id": "benchmark-20260910T122228Z-3e2b37",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local",
  "source_revision": "b298ba4ef5da37ca24269d38b1f85dc0d7f90826",
  "evidence": [
    "manifest.json",
    "iterations.csv",
    "summary.json"
  ]
}
```

Wersja przypadków: `2`. Liczby: `{'invoice_math': 13, 'url_router': 12, 'job_queue': 12}`.

Tryb: **live**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

**Przebieg pilotażowy — nie używać do rankingu końcowego.** Diagnostic v2 run: GPT6 local adapter could not resume a failed task at unchanged SHA. GLM53 and Opus5 completed 37/37; GPT6 is rerun separately after adapter correction.

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 6 | 5/9 | 3/3 | 37/37 | 2 | 17 | 30443 | 321.142 |
| gpt6 | 3 | 3/9 | 1/3 | 20/37 | 5 | 14 | 16075 | 158.022 |
| opus5 | 4 | 9/9 | 3/3 | 37/37 | 0 | 8 | 9606 | 110.476 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | repaired | 4/4 | True | 36.406 |
| glm53 | invoice_math | 2 | error | 5/9 | False | 68.022 |
| glm53 | invoice_math | 3 | repaired | 13/13 | True | 42.601 |
| glm53 | job_queue | 1 | repaired | 4/4 | True | 27.645 |
| glm53 | job_queue | 2 | error | 6/8 | False | 53.305 |
| glm53 | job_queue | 3 | repaired | 12/12 | True | 30.179 |
| glm53 | url_router | 1 | rejected | 3/4 | False | 28.094 |
| glm53 | url_router | 2 | partial_improvement | 6/7 | True | 11.342 |
| glm53 | url_router | 3 | repaired | 12/12 | True | 23.548 |
| gpt6 | invoice_math | 1 | error | 1/4 | False | 6.077 |
| gpt6 | invoice_math | 2 | error | 2/9 | False | 8.142 |
| gpt6 | invoice_math | 3 | error | 3/13 | False | 14.893 |
| gpt6 | job_queue | 1 | repaired | 4/4 | True | 27.646 |
| gpt6 | job_queue | 2 | repaired | 8/8 | True | 22.625 |
| gpt6 | job_queue | 3 | repaired | 12/12 | True | 30.008 |
| gpt6 | url_router | 1 | rejected | 3/4 | False | 29.068 |
| gpt6 | url_router | 2 | error | 4/7 | False | 16.414 |
| gpt6 | url_router | 3 | error | 5/12 | False | 3.149 |
| opus5 | invoice_math | 1 | repaired | 4/4 | True | 22.224 |
| opus5 | invoice_math | 2 | repaired | 9/9 | True | 29.907 |
| opus5 | invoice_math | 3 | already_green | 13/13 | False | 0.257 |
| opus5 | job_queue | 1 | repaired | 4/4 | True | 32.476 |
| opus5 | job_queue | 2 | already_green | 8/8 | False | 0.59 |
| opus5 | job_queue | 3 | already_green | 12/12 | False | 0.577 |
| opus5 | url_router | 1 | repaired | 4/4 | True | 22.793 |
| opus5 | url_router | 2 | already_green | 7/7 | False | 0.784 |
| opus5 | url_router | 3 | already_green | 12/12 | False | 0.868 |

## Interpretacja i ograniczenia

To benchmark lokalnych komponentów naprawczych z adapterami, a nie pełnych wdrożeń
GitHub Actions. Jedna próba na każdą parę rozwiązanie–projekt; brak podstaw do istotności
statystycznej lub wnioskowania o działaniu nieskończonej pętli. Wspólny model i kolejność
sekwencyjna mogą wpływać na opóźnienia dostawcy oraz cache. Czas nie stanowi rankingu modeli.

- GLM53: oryginalny krytyk/wybór, generator patcha i walidator; lokalny most testów i commitów.
- GPT6: oryginalne kontrakty, scorer, walidatory planu i patcha; lokalny most kontrolera
  i informacji zwrotnej. Nie uruchamiano produkcyjnej maszyny stanów GitHub, polityk merge,
  ani czasowego cooldownu między zadaniami (nowa grupa testów w każdym etapie).
- Opus5: oryginalna pętla wyboru z lokalnym transportem faktów oraz **dodany wykonawca
  benchmarku**. Ten przebieg nie wywołuje nowego natywnego modułu `repair`.
  Jego skuteczność wykonawcza dotyczy tej kompozycji, nie pełnej pętli produktu Opus5.

Każdy projekt startuje z identycznego błędnego kodu. Wszystkie trzy usterki są obecne od
początku; w kolejnych iteracjach ujawniane są testy kumulatywnie (liczby przypadków określa wersja zestawu w manifeście). Wcześniejsze
poprawki pozostają. Pełny zewnętrzny oracle jest uruchamiany także przed i po patchu;
jego przyszłe przypadki nie są przekazywane LLM. Każda nowa regresja odrzuca patch.
Poprawka jest przyjmowana tylko przy zwiększeniu liczby zaliczonych testów bieżącego
etapu. Już zielony etap wykonuje no-op bez LLM. `27 iteracji` nie oznacza 27 przyjętych
poprawek. Liczba przyjętych poprawek sama w sobie nie jest rankingiem: lepsza poprawka
może naprawić przyszłe błędy wcześniej i zmniejszyć liczbę późniejszych zmian.

Testy są niezmienne i znajdują się poza edytowanym projektem. Kod wykonywany jest w
osobnym procesie bez sekretów w środowisku; proces nie jest sandboxem systemowym.
Nie tworzono issues, PR ani zdalnych commitów. Raporty, różnice i podsumowania są
lokalne. Koszt jest dostępny tylko, jeśli SDK zwróci metadane kosztu; brak ceny nie
jest zerowym kosztem. Tokeny błędnych żądań bez usage pozostają nieznane.

## Artefakty

- [Manifest konfiguracji i skrótów źródeł](manifest.json)
- [Podsumowanie JSON](summary.json)
- [Wszystkie iteracje CSV](iterations.csv)
- `iterations/`: metryki, błędy, testy przed/po i metadane wywołań.
- `patches/`: rzeczywiste patche, także odrzucone.
- `final/`: końcowy kod i wynik pełnego oracle dla każdej pary.
- Repos i stan roboczy pozostają w prywatnym katalogu wskazanym w manifeście.
