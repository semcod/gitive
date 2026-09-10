# Benchmark napraw — 20260910T120448Z-4012c1

```json
{
  "id": "benchmark-20260910T120448Z-4012c1",
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

Tryb: **live**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 6 | 9/9 | 3/3 | 27/27 | 0 | 12 | 14448 | 146.255 |
| gpt6 | 4 | 8/9 | 3/3 | 27/27 | 1 | 9 | 9298 | 35.647 |
| opus5 | 6 | 9/9 | 3/3 | 27/27 | 0 | 12 | 12683 | 90.042 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | repaired | 3/3 | True | 27.773 |
| glm53 | invoice_math | 2 | already_green | 6/6 | False | 0.48 |
| glm53 | invoice_math | 3 | already_green | 9/9 | False | 0.445 |
| glm53 | job_queue | 1 | repaired | 3/3 | True | 16.209 |
| glm53 | job_queue | 2 | repaired | 6/6 | True | 33.48 |
| glm53 | job_queue | 3 | already_green | 9/9 | False | 0.542 |
| glm53 | url_router | 1 | repaired | 3/3 | True | 26.672 |
| glm53 | url_router | 2 | repaired | 6/6 | True | 28.179 |
| glm53 | url_router | 3 | repaired | 9/9 | True | 12.475 |
| gpt6 | invoice_math | 1 | repaired | 3/3 | True | 4.688 |
| gpt6 | invoice_math | 2 | already_green | 6/6 | False | 0.555 |
| gpt6 | invoice_math | 3 | already_green | 9/9 | False | 0.661 |
| gpt6 | job_queue | 1 | repaired | 3/3 | True | 8.962 |
| gpt6 | job_queue | 2 | already_green | 6/6 | False | 0.432 |
| gpt6 | job_queue | 3 | already_green | 9/9 | False | 1.176 |
| gpt6 | url_router | 1 | error | 2/3 | False | 1.587 |
| gpt6 | url_router | 2 | repaired | 6/6 | True | 12.311 |
| gpt6 | url_router | 3 | repaired | 9/9 | True | 5.275 |
| opus5 | invoice_math | 1 | repaired | 3/3 | True | 9.199 |
| opus5 | invoice_math | 2 | repaired | 6/6 | True | 14.749 |
| opus5 | invoice_math | 3 | already_green | 9/9 | False | 0.501 |
| opus5 | job_queue | 1 | repaired | 3/3 | True | 19.513 |
| opus5 | job_queue | 2 | already_green | 6/6 | False | 0.556 |
| opus5 | job_queue | 3 | already_green | 9/9 | False | 0.696 |
| opus5 | url_router | 1 | repaired | 3/3 | True | 18.987 |
| opus5 | url_router | 2 | repaired | 6/6 | True | 15.33 |
| opus5 | url_router | 3 | repaired | 9/9 | True | 10.511 |

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

## Zapisy LLM i dodatkowa analiza

- [Indeks requestów i odpowiedzi oraz metryki](transcript-audit.json)
- [Kontrola kompletności i uprawnień](capture-verification.json)
- [Dodatkowe przypadki poza pierwotnym wynikiem](edge-case-audit.json)
- [Analiza jakości odpowiedzi](../../../docs/analysis/llm-transcript-quality-2026-09-10.md)
