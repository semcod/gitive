# Benchmark napraw — 20260910T130429Z-63a387

```json
{
  "id": "benchmark-20260910T130429Z-63a387",
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

Tryb: **mock**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

**Test infrastruktury: brak wywołań LLM; wyniki nie mierzą skuteczności napraw.**

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 0 | 0/9 | 0/3 | 15/37 | 0 | 0 | 0 | 2.913 |
| gpt6 | 0 | 0/9 | 0/3 | 15/37 | 0 | 0 | 0 | 2.506 |
| opus5 | 0 | 0/9 | 0/3 | 15/37 | 0 | 0 | 0 | 2.55 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | mock_no_repair | 1/4 | False | 0.398 |
| glm53 | invoice_math | 2 | mock_no_repair | 2/9 | False | 0.316 |
| glm53 | invoice_math | 3 | mock_no_repair | 3/13 | False | 0.301 |
| glm53 | job_queue | 1 | mock_no_repair | 2/4 | False | 0.314 |
| glm53 | job_queue | 2 | mock_no_repair | 4/8 | False | 0.28 |
| glm53 | job_queue | 3 | mock_no_repair | 7/12 | False | 0.243 |
| glm53 | url_router | 1 | mock_no_repair | 3/4 | False | 0.501 |
| glm53 | url_router | 2 | mock_no_repair | 4/7 | False | 0.302 |
| glm53 | url_router | 3 | mock_no_repair | 5/12 | False | 0.258 |
| gpt6 | invoice_math | 1 | mock_no_repair | 1/4 | False | 0.297 |
| gpt6 | invoice_math | 2 | mock_no_repair | 2/9 | False | 0.281 |
| gpt6 | invoice_math | 3 | mock_no_repair | 3/13 | False | 0.248 |
| gpt6 | job_queue | 1 | mock_no_repair | 2/4 | False | 0.278 |
| gpt6 | job_queue | 2 | mock_no_repair | 4/8 | False | 0.272 |
| gpt6 | job_queue | 3 | mock_no_repair | 7/12 | False | 0.271 |
| gpt6 | url_router | 1 | mock_no_repair | 3/4 | False | 0.256 |
| gpt6 | url_router | 2 | mock_no_repair | 4/7 | False | 0.299 |
| gpt6 | url_router | 3 | mock_no_repair | 5/12 | False | 0.304 |
| opus5 | invoice_math | 1 | mock_no_repair | 1/4 | False | 0.276 |
| opus5 | invoice_math | 2 | mock_no_repair | 2/9 | False | 0.28 |
| opus5 | invoice_math | 3 | mock_no_repair | 3/13 | False | 0.342 |
| opus5 | job_queue | 1 | mock_no_repair | 2/4 | False | 0.261 |
| opus5 | job_queue | 2 | mock_no_repair | 4/8 | False | 0.264 |
| opus5 | job_queue | 3 | mock_no_repair | 7/12 | False | 0.313 |
| opus5 | url_router | 1 | mock_no_repair | 3/4 | False | 0.257 |
| opus5 | url_router | 2 | mock_no_repair | 4/7 | False | 0.264 |
| opus5 | url_router | 3 | mock_no_repair | 5/12 | False | 0.293 |

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
