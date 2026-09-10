# Wdrożenie poprawek po benchmarku

```json
{
  "id": "benchmark-fixes-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "9f6c7b1e9b8bc3475c7ec2e74a39b36039f5321a",
  "evidence": [
    "benchmark/native-runs/20260910T112057Z/glm53.json",
    "benchmark/native-runs/20260910T112058Z/opus5.json",
    "glm53/tests/test_integration.py",
    "gpt6/tests_github/test_integration.py",
    "opus5/tests/test_repair.py"
  ]
}
```

## Zmiany

Na podstawie [analizy benchmarku](benchmark-improvements-2026-09-10.md) wdrożono poprawki funkcjonalne i testy. Zmiany są lokalne, bez commita i publikacji GitHub.

**GLM53:** `refactor --repair-base` dopuszcza nieprzechodzące testy bazowe i przekazuje ich wynik do propozycji oraz wykonania. Akceptacja wymaga przejścia całego zestawu testów — częściowa poprawa nie wystarcza. `--apply` zapisuje lokalnie zaakceptowany kod i pamięć przez fast-forward z tymczasowego klona. Odrzucony kod zostaje wycofany, a obserwacja niepowodzenia trafia do pamięci. `--publish` i `--apply` wykluczają się. Podgląd nie wymaga repozytorium GitHub.

Nagrody `knowledge_reward` i `learning_reward` są oddzielne. Dla wykonania naprawy model otrzymuje `execution_reward` 0/1; nowy fakt o błędzie nie zwiększa nagrody za sukces. Replay obsługuje też starsze wpisy. Klient zapisuje czas, tokeny, dostępny koszt SDK, fazę i zakończenie odpowiedzi, także przy błędnym JSON. `LLM_MAX_CALLS` ogranicza wywołania jednej instancji klienta (domyślnie 20); CLI współdzieli ją między krokami `run`. Automatyczne ponowienia SDK wyłączono, aby nie omijały tego limitu. Nie jest to trwały budżet dzienny między procesami.

**GPT6:** walidacja wskazuje ścieżkę, wymagane brakujące pola i liczbę nadmiarowych kluczy, bez wypisywania ich potencjalnie wrażliwej treści. Kontrakty pustego wyniku zachowują wymagane pola. Opcjonalne `LLM_JSON_SCHEMA=true` przesyła osobny ścisły schemat wynikający z kontraktu propozycji lub poprawki; domyślnie pozostaje kompatybilny tryb JSON object. Wsparcie konkretnej trasy dostawcy dla schematów wymaga sprawdzenia przed włączeniem. Lokalne kontrole SHA, ścieżek i dowodów pozostają obowiązkowe.

Nieudana propozycja zapisuje `plan_failure` w pamięci Git. Następny cykl przekazuje bezpieczną diagnostykę walidacji i ponawia próbę. Liczba prób tego samego kontekstu jest ograniczona przez `max_attempts_per_issue`; limity cyklu i dnia nadal obowiązują. Błąd kontraktu po odpowiedzi nie gubi informacji o zużytych tokenach. Testy obejmują restart po błędnej propozycji, odzyskanie działania, nieudane testy poprawki i kolejną próbę.

**Opus5:** parser rozumie nawiasy i cudzysłowy wewnątrz napisów, najpierw parsuje pełny JSON i odrzuca niepoprawne elementy zamiast je pomijać. Klient ma jawny timeout, zero ukrytych ponowień oraz odrębne błędy transportu, pustej treści, niepełnej odpowiedzi i JSON. Ostatnie dostępne dane użycia można odczytać przez `complete.last_usage`; nie jest to trwały licznik budżetu.

Nowe `repair` wykonuje istniejące zadanie z lokalnego ledgeru. W tymczasowym klonie edytuje tylko wskazane istniejące pliki źródłowe, uruchamia zaufaną komendę testów bez kluczy LLM/GitHub w środowisku i przyjmuje wyłącznie kompletnie zielony wynik. Niepowodzenie wycofuje kod. Wynik próby i oddzielne wagi skuteczności wykonania zapisuje w `.intuition-repair/`, w tym samym commicie co zaakceptowana poprawka. Aktualizacja oryginalnego repozytorium wymaga czystego checkoutu, niezmienionego HEAD i fast-forward. Blokada wyklucza jednoczesne lokalne naprawy. Zielona baza kończy się bez kolejnego wywołania LLM.

## Użycie

GLM53, po inicjalizacji pamięci w docelowym repozytorium:

```bash
PYTHONPATH=glm53 python3 -m intuition --root /sciezka/do/projektu refactor \
  --repair-base --apply --allow src \
  --test '["python3","-B","-m","unittest","discover","-s","tests"]'
```

Istniejący projekt GLM53 powinien ignorować `.intuition.lock` i `.intuition-pending.json`. Pominięcie `--apply` wykonuje podgląd. Komenda testów musi sprawdzać również wcześniej poprawne zachowania.

Opus5, dla zadania utworzonego przez natywny `cycle` w lokalnym ledgerze (wymagane pola `files` i `phi`):

```bash
PYTHONPATH=opus5/src python3 -m intuition.cli repair \
  --repo-root /sciezka/do/projektu --task-id IDENTYFIKATOR_Z_LEDGERU \
  --test '["python3","-B","-m","unittest","discover","-s","tests"]'
```

`INTUITION_ROOT` wskazuje katalog ledgeru. Wspólne ustawienia LiteLLM pozostają w głównym `.env`; klucze nie są kopiowane do repozytoriów testowych. Wykonanie testów nie jest izolacją systemową: używać kontrolowanych lokalnych projektów i zaufanej komendy testującej.

## Weryfikacja

- GLM53: 25 testów, w tym czerwona baza, odrzucenie regresji, rozdzielone nagrody, replay i limit wywołań.
- GPT6: 25 testów silnika Python, zestaw TypeScript i porównanie implementacji oraz 74 testy integracji/kontraktów GitHub. TypeScript uruchomiono na Node 22.23.1.
- Opus5: 14 dotychczasowych testów i 3 nowe testy parsera, transportu oraz cyklu odrzucenie → akceptacja → wznowienie. Runner offline odkrywa teraz wszystkie pliki `test_*.py`.
- Benchmark: 6 testów infrastruktury i adapterów.
- [GLM53 native](../../benchmark/native-runs/20260910T112057Z/glm53.json) i [Opus5 native](../../benchmark/native-runs/20260910T112058Z/opus5.json): każdy 3 projekty i 27/27 przypadków. Użyto zapisanych poprawek z poprzedniego benchmarku przez rodzime wykonawce, bez adaptera wykonania benchmarku i bez płatnych zapytań. GLM53 dodatkowo sprawdza replay pamięci.

Powtarzalne sprawdzenie natywnych wykonawców: `make test-native-repair`; wyniki mają timestamp w `benchmark/native-runs/`.

## Granice wyniku i dalsze pomiary

Nie wykonano nowego benchmarku live ani statystycznego porównania 5–10 powtórzeń. Nie ma podstaw do twierdzenia, że zmiany obniżyły koszt lub zwiększyły skuteczność odpowiedzi modelu. Skracanie kontekstu i optymalizacja kosztu pozostają eksperymentami wymagającymi takiego pomiaru. Nie uruchamiano publikacji issues, PR ani merge na GitHubie.

Opus5 wykonuje zadanie z ledgeru; nowy moduł nie dodaje automatycznej publikacji PR. Wyniki kontrolowanych testów potwierdzają lokalny proces wykonania, a nie pełny bezobsługowy proces GitHub. Trwały budżet dzienny i pełny dziennik telemetrii dla Opus5/GLM53 pozostają osobnym rozszerzeniem.
