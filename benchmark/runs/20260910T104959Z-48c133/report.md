# Benchmark napraw — 20260910T104959Z-48c133

```json
{
  "id": "benchmark-20260910T104959Z-48c133",
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

Tryb: **live**. Zapisane iteracje: **27/27**. Model: `openrouter/z-ai/glm-5.3`.

## Wyniki

| Rozwiązanie | Przyjęte poprawki | Zielone etapy | Końcowo zielone projekty | Końcowe testy | Błędy adaptera | LLM | Tokeny | Czas s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glm53 | 5 | 9/9 | 3/3 | 27/27 | 0 | 10 | 11628 | 160.933 |
| gpt6 | 4 | 8/9 | 3/3 | 27/27 | 1 | 9 | 10238 | 101.789 |
| opus5 | 5 | 8/9 | 3/3 | 27/27 | 1 | 11 | 11337 | 155.651 |

## Trajektorie

| Rozwiązanie | Projekt | Iteracja | Wynik | Testy etapu | Przyjęto | Czas s |
|---|---|---:|---|---:|---|---:|
| glm53 | invoice_math | 1 | repaired | 3/3 | True | 17.848 |
| glm53 | invoice_math | 2 | already_green | 6/6 | False | 0.398 |
| glm53 | invoice_math | 3 | already_green | 9/9 | False | 0.431 |
| glm53 | job_queue | 1 | repaired | 3/3 | True | 45.134 |
| glm53 | job_queue | 2 | already_green | 6/6 | False | 0.306 |
| glm53 | job_queue | 3 | already_green | 9/9 | False | 0.242 |
| glm53 | url_router | 1 | repaired | 3/3 | True | 29.372 |
| glm53 | url_router | 2 | repaired | 6/6 | True | 33.477 |
| glm53 | url_router | 3 | repaired | 9/9 | True | 33.725 |
| gpt6 | invoice_math | 1 | repaired | 3/3 | True | 44.301 |
| gpt6 | invoice_math | 2 | already_green | 6/6 | False | 0.212 |
| gpt6 | invoice_math | 3 | already_green | 9/9 | False | 0.221 |
| gpt6 | job_queue | 1 | repaired | 3/3 | True | 7.857 |
| gpt6 | job_queue | 2 | already_green | 6/6 | False | 0.267 |
| gpt6 | job_queue | 3 | already_green | 9/9 | False | 0.229 |
| gpt6 | url_router | 1 | repaired | 3/3 | True | 8.771 |
| gpt6 | url_router | 2 | error | 4/6 | False | 1.066 |
| gpt6 | url_router | 3 | repaired | 9/9 | True | 38.865 |
| opus5 | invoice_math | 1 | error | 1/3 | False | 21.882 |
| opus5 | invoice_math | 2 | repaired | 6/6 | True | 34.186 |
| opus5 | invoice_math | 3 | already_green | 9/9 | False | 0.207 |
| opus5 | job_queue | 1 | repaired | 3/3 | True | 32.804 |
| opus5 | job_queue | 2 | already_green | 6/6 | False | 0.303 |
| opus5 | job_queue | 3 | already_green | 9/9 | False | 0.331 |
| opus5 | url_router | 1 | repaired | 3/3 | True | 21.312 |
| opus5 | url_router | 2 | repaired | 6/6 | True | 16.519 |
| opus5 | url_router | 3 | repaired | 9/9 | True | 28.107 |

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

## Wnioski z tego przebiegu

Wszystkie trzy kompozycje doprowadziły wszystkie projekty do pełnego wyniku 9/9 testów.
GLM53 miał 9/9 zielonych etapów; GPT6 oraz Opus5 z wykonawcą miały po 8/9. GPT6 odrzucił
format JSON w drugiej iteracji routera i naprawił projekt w trzeciej. Parser Opus5 odrzucił
pierwszą propozycję kalkulatora; druga iteracja naprawiła cały projekt. Nie przypisujemy
błędów parsowania samemu modelowi bez analizy pełnej odpowiedzi i parsera.

Łącznie wykonano 30 wywołań LLM, rozliczono 33 203 tokeny, a suma kosztów przekazanych
przez SDK wyniosła 0,072835 USD. Są to metadane tego właściwego przebiegu, bez pilotażu;
nie jest to odczyt rachunku konta. Czas jest silnie zależny od opóźnień dostawcy.
Nie ma podstaw do wyłonienia uniwersalnie najlepszego rozwiązania na podstawie jednej
próby i trzech niewielkich projektów.

[Kontrola kompletności i zgodności pomiarów](verification.json) potwierdza 27 rekordów,
9 zakończonych par, identyczny kod startowy, brak zmian źródeł w czasie pomiaru i
zachowanie zasad przyjmowania/wycofywania poprawek. Dane stanowią lokalny raport;
nie utworzono PR ani zdalnej publikacji.
