# Benchmark napraw — 20260910T123602Z-51ced9

```json
{
  "id": "benchmark-20260910T123602Z-51ced9",
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

Tryb: **live**. Zapisane iteracje: **9/9**. Model: `openrouter/z-ai/glm-5.3`.

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gpt6 | 6 | 8/9 | 3/3 | 37/37 | 1 | 13 | 15541 | 52.55 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| gpt6 | invoice_math | 1 | repaired | 4/4 | True | 13.64 |
| gpt6 | invoice_math | 2 | already_green | 9/9 | False | 0.473 |
| gpt6 | invoice_math | 3 | already_green | 13/13 | False | 0.432 |
| gpt6 | job_queue | 1 | error | 2/4 | False | 7.449 |
| gpt6 | job_queue | 2 | repaired | 8/8 | True | 3.441 |
| gpt6 | job_queue | 3 | repaired | 12/12 | True | 5.17 |
| gpt6 | url_router | 1 | repaired | 4/4 | True | 7.219 |
| gpt6 | url_router | 2 | repaired | 7/7 | True | 5.885 |
| gpt6 | url_router | 3 | repaired | 12/12 | True | 8.841 |

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
