# Benchmark napraw — 20260910T132550Z-6f91fc

```json
{
  "id": "benchmark-20260910T132550Z-6f91fc",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local",
  "source_revision": "9bf5c8618de5b1b1cf7edf93a27394298999381e",
  "evidence": [
    "manifest.json",
    "iterations.csv",
    "summary.json"
  ]
}
```

Wersja przypadków: `2`. Liczby: `{'invoice_math': 13, 'url_router': 12, 'job_queue': 12}`.

Tryb: **live**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 4 | 7/9 | 1/3 | 32/37 | 2 | 12 | 15114 | 49.798 |
| gpt6 | 3 | 6/9 | 2/3 | 30/37 | 1 | 10 | 15821 | 55.741 |
| opus5 | 3 | 3/9 | 1/3 | 25/37 | 6 | 18 | 20205 | 160.289 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | repaired | 4/4 | True | 5.061 |
| glm53 | invoice_math | 2 | already_green | 9/9 | False | 0.266 |
| glm53 | invoice_math | 3 | already_green | 13/13 | False | 0.26 |
| glm53 | job_queue | 1 | repaired | 4/4 | True | 6.68 |
| glm53 | job_queue | 2 | already_green | 8/8 | False | 0.253 |
| glm53 | job_queue | 3 | error | 11/12 | False | 9.301 |
| glm53 | url_router | 1 | repaired | 4/4 | True | 6.155 |
| glm53 | url_router | 2 | repaired | 7/7 | True | 7.996 |
| glm53 | url_router | 3 | error | 8/12 | False | 13.826 |
| gpt6 | invoice_math | 1 | repaired | 4/4 | True | 4.784 |
| gpt6 | invoice_math | 2 | already_green | 9/9 | False | 0.264 |
| gpt6 | invoice_math | 3 | already_green | 13/13 | False | 0.409 |
| gpt6 | job_queue | 1 | repaired | 4/4 | True | 10.695 |
| gpt6 | job_queue | 2 | repaired | 8/8 | True | 5.522 |
| gpt6 | job_queue | 3 | already_green | 12/12 | False | 0.25 |
| gpt6 | url_router | 1 | rejected | 3/4 | False | 6.499 |
| gpt6 | url_router | 2 | rejected | 4/7 | False | 3.06 |
| gpt6 | url_router | 3 | error | 5/12 | False | 24.258 |
| opus5 | invoice_math | 1 | repaired | 4/4 | True | 14.669 |
| opus5 | invoice_math | 2 | repaired | 9/9 | True | 17.113 |
| opus5 | invoice_math | 3 | repaired | 13/13 | True | 15.495 |
| opus5 | job_queue | 1 | error | 2/4 | False | 6.816 |
| opus5 | job_queue | 2 | error | 4/8 | False | 15.042 |
| opus5 | job_queue | 3 | error | 7/12 | False | 33.548 |
| opus5 | url_router | 1 | error | 3/4 | False | 28.243 |
| opus5 | url_router | 2 | error | 4/7 | False | 14.754 |
| opus5 | url_router | 3 | error | 5/12 | False | 14.609 |

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
