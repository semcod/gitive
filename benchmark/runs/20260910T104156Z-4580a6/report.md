# Benchmark napraw — 20260910T104156Z-4580a6

```json
{
  "id": "benchmark-20260910T104156Z-4580a6",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local",
  "source_revision": "9f6c7b1e9b8bc3475c7ec2e74a39b36039f5321a",
  "evidence": [
    "manifest.json",
    "iterations.csv",
    "summary.json"
  ]
}
```

Tryb: **mock**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

**Test infrastruktury: brak wywołań LLM; wyniki nie mierzą skuteczności napraw.**

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 0 | 0/9 | 0/3 | 11/27 | 0 | 0 | 0 | 3.012 |
| gpt6 | 0 | 0/9 | 0/3 | 11/27 | 0 | 0 | 0 | 2.83 |
| opus5 | 0 | 0/9 | 0/3 | 11/27 | 0 | 0 | 0 | 3.569 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | mock_no_repair | 1/3 | False | 0.401 |
| glm53 | invoice_math | 2 | mock_no_repair | 2/6 | False | 0.32 |
| glm53 | invoice_math | 3 | mock_no_repair | 2/9 | False | 0.327 |
| glm53 | job_queue | 1 | mock_no_repair | 2/3 | False | 0.31 |
| glm53 | job_queue | 2 | mock_no_repair | 3/6 | False | 0.353 |
| glm53 | job_queue | 3 | mock_no_repair | 5/9 | False | 0.368 |
| glm53 | url_router | 1 | mock_no_repair | 2/3 | False | 0.308 |
| glm53 | url_router | 2 | mock_no_repair | 3/6 | False | 0.303 |
| glm53 | url_router | 3 | mock_no_repair | 4/9 | False | 0.322 |
| gpt6 | invoice_math | 1 | mock_no_repair | 1/3 | False | 0.343 |
| gpt6 | invoice_math | 2 | mock_no_repair | 2/6 | False | 0.336 |
| gpt6 | invoice_math | 3 | mock_no_repair | 2/9 | False | 0.321 |
| gpt6 | job_queue | 1 | mock_no_repair | 2/3 | False | 0.251 |
| gpt6 | job_queue | 2 | mock_no_repair | 3/6 | False | 0.264 |
| gpt6 | job_queue | 3 | mock_no_repair | 5/9 | False | 0.293 |
| gpt6 | url_router | 1 | mock_no_repair | 2/3 | False | 0.324 |
| gpt6 | url_router | 2 | mock_no_repair | 3/6 | False | 0.306 |
| gpt6 | url_router | 3 | mock_no_repair | 4/9 | False | 0.392 |
| opus5 | invoice_math | 1 | mock_no_repair | 1/3 | False | 0.411 |
| opus5 | invoice_math | 2 | mock_no_repair | 2/6 | False | 0.363 |
| opus5 | invoice_math | 3 | mock_no_repair | 2/9 | False | 0.429 |
| opus5 | job_queue | 1 | mock_no_repair | 2/3 | False | 0.403 |
| opus5 | job_queue | 2 | mock_no_repair | 3/6 | False | 0.493 |
| opus5 | job_queue | 3 | mock_no_repair | 5/9 | False | 0.322 |
| opus5 | url_router | 1 | mock_no_repair | 2/3 | False | 0.379 |
| opus5 | url_router | 2 | mock_no_repair | 3/6 | False | 0.391 |
| opus5 | url_router | 3 | mock_no_repair | 4/9 | False | 0.378 |

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
  benchmarku**, ponieważ projekt natywnie kończy pracę na utworzeniu zadania.
  Jego skuteczność wykonawcza dotyczy tej kompozycji, nie samego produktu Opus5.

Każdy projekt startuje z identycznego błędnego kodu. Wszystkie trzy usterki są obecne od
początku; w kolejnych iteracjach ujawniane są testy kumulatywnie (3, 6, 9). Wcześniejsze
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
