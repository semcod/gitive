# Poprawki jakości i benchmark wersji 2

```json
{
  "id": "quality-fixes-v2-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "b298ba4ef5da37ca24269d38b1f85dc0d7f90826",
  "evidence": [
    "benchmark/runs/20260910T122228Z-3e2b37/manifest.json",
    "benchmark/runs/20260910T122228Z-3e2b37/summary.json",
    "glm53/tests/test_quality.py",
    "gpt6/tests_github/test_contracts.py",
    "opus5/tests/test_quality.py",
    "benchmark/tests/test_benchmark.py"
  ]
}
```

## Zakres zmian

Wdrożono poprawki wynikające z [analizy pełnych odpowiedzi](llm-transcript-quality-2026-09-10.md). Nie zmieniano kontrolowanego, błędnego kodu początkowego projektów. Poprawiono generatory, walidatory i zakres testów; zachowano historyczne raporty.

### Wspólna ochrona API

Każdy projekt otrzymał niezależny moduł stdlib `api_guard.py`, podłączony do jego ścieżki walidacji poprawek Pythona. Guard porównuje AST publicznych funkcji i metod: argumenty, wartości domyślne, adnotacje, dekoratory oraz konstruktor `__init__`, `__new__` i `__call__`. Odrzuca zmianę podpisu `taxed(amount, percent)` na wariant z opcjonalnym trzecim parametrem, usunięcie funkcji i nowe publiczne funkcje. Zmiana implementacji z zachowaniem sygnatury jest dozwolona; pomocnicze funkcje prywatne pozostają możliwe.

To statyczna ochrona zdefiniowanych callable, nie kompletny dowód kompatybilności API. Nie weryfikuje dowolnej semantyki, aliasów importów ani dynamicznie tworzonych obiektów. Typ i wartość wyniku wymagają testów uruchomieniowych.

### GLM53

- Prompt wymaga zachowania sygnatur, typów wyników i serializowalności JSON; zabrania nieuzasadnionego clamp i zaokrąglania.
- Niewykonanych przykładów nie należy przedstawiać jako sprawdzonych; generator ma proponować weryfikowalne kryteria zamiast deklarować z pamięci wynik `round` czy zachowanie sortowania.
- Digest pomija zastąpione fakty. Historia append-only pozostaje zachowana.
- Adapter benchmarku łączy kolejne wyniki CI przez `supersedes` i przekazuje do uczenia `execution_reward=0/1`. Nowy opis błędu nie jest nagrodą za skuteczną naprawę.

Zmiana promptu nie gwarantuje prawdziwości wszystkich uzasadnień. Rzeczywistym dowodem wyniku pozostają testy; pełne odpowiedzi nadal są zapisywane do późniejszej kontroli.

### GPT6

- Walidator odrzuca rozpoznane placeholdery, w tym zaobserwowane `acceptance_placeholder_2`, w kryteriach odbioru.
- Każdy request otrzymuje przykład poprawnej pustej odpowiedzi z faktycznym `base_sha` i polami odpowiednimi dla fazy. `{}` nadal jest odrzucane; nie uzupełnia się go planem wymyślonym przez kontroler.
- Budżet wejścia uwzględnia również ten dynamiczny fragment promptu.
- Patch musi zachować publiczną sygnaturę Pythona. Prompt rozdziela kontrakt procentów od niezamówionego clamp, zaokrąglania i przeciążeń API.
- Adapter zachowuje historię faktów, lecz do planowania kolejnego etapu przekazuje bieżący wynik testów.

Walidacja placeholderów nie jest pełną oceną jakości każdego zdania. Pozostaje rodzima, ograniczona obsługa ponowień planu w kontrolerze; lokalny adapter benchmarku nie zastępuje jej pełnym procesem GitHub.

### Opus5

- Natywne `cycle` przyjmuje kontekst kodu i przed rankingiem odrzuca zadania poza dozwolonymi plikami, z placeholderami lub niepoprawnym kosztem.
- CLI `cycle --allow src` oraz `INTUITION_ALLOWED_PATHS=src` włączają odczyt ograniczonego, śledzonego kodu do promptu. Kontrola pomija testy, ukryte ścieżki, dowiązania i zbyt duże pliki. Bez skonfigurowanego zakresu zachowany jest ogólny tryb proponowania issues.
- Fakty oznaczone jako zastąpione lub rozstrzygnięte nie wchodzą ponownie do aktywnego kontekstu i rankingu. W benchmarku kolejne wyniki CI są jawnie połączone przez `supersedes`.
- Zarówno natywny `repair`, jak i adapter benchmarku wywołują kontrolę sygnatur przed zastosowaniem patcha.
- Prompt wyjaśnia, że nieudany test istnieje; nie wolno wnioskować z jego błędu, że dany przypadek jest nietestowany.

Dla zdalnego CI potrzebne jest prawidłowe oznaczenie rozstrzygniętych obserwacji przez transport. Kod nie zakłada, że dowolny nowszy zielony run automatycznie rozstrzyga wszystkie starsze awarie z innych gałęzi czy workflowów.

## Wersja 2 przypadków

Zestaw ustalono przed uruchomieniem live, identycznie dla wszystkich rozwiązań:

| Projekt | Przypadki | Nowe wymagania |
|---|---:|---|
| invoice_math | 13 | dodatkowy rabat/podatek, podatek od 0.01 bez kwantyzacji do centów, HALF_UP dla 0.005 |
| url_router | 12 | prefiks zakończony `/`, dekodowanie nazwy parametru, zakodowany plus `%2B` |
| job_queue | 12 | ujemne priorytety, ponowienie przed limitem, zachowanie pierwszego pełnego rekordu |

Oracle sprawdza też typ wyniku i serializowalność JSON. Wynik `Decimal` numerycznie równy oczekiwanej liczbie nie jest uznawany za zachowanie kontraktu int/float. Nowe przypadki są przypisane do odpowiednich etapów; pozostałe etapy nadal są ukryte przed generatorem i służą kontroli regresji.

Nowa suma to **37 testów na rozwiązanie**, trzy iteracje na każdy z trzech projektów, czyli nadal **27 iteracji benchmarku**. Liczby etapów kumulatywnych zależą teraz od projektu. Wyników v2 nie należy porównywać bezpośrednio procentowo z wcześniejszymi 27 testami. Kod początkowy pozostał identyczny; zmieniły się wymagania i kontekst planowania.

## Wyniki

RESULTS_PENDING

## Weryfikacja i ograniczenia

TESTS_PENDING

Benchmark zachowuje pełny prywatny zapis requestów i odpowiedzi LiteLLM, z receiptami i SHA-256. Wersja przypadków oraz skróty źródeł są zapisane w manifeście. Testy symulujące SDK są oddzielone od przebiegu live.

Nadal jest to lokalne porównanie komponentów i adapterów wykonania, nie test produkcyjnego Issue → PR → merge → release. Nie zmieniano reguł GitHub, nie tworzono zdalnych zgłoszeń, PR ani tagów. Zmiany pozostają lokalne, bez commita.
