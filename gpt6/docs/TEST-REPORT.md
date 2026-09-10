# Raport testów — Intuition GitHub 2.0

Data: **10 września 2026**. Testy wykonano lokalnie podczas przygotowania paczki, a nie na uwierzytelnionym koncie GitHub.

## Wynik

| Zestaw | Wynik |
|---|---:|
| Zachowany model Python v1 | **25 / 25** |
| Zachowany model TypeScript v1 | **25 / 25** |
| Nowe testy kontraktów, integracji i plików projektu | **71 / 71** |
| Razem testy jednostkowe/integracyjne | **121 / 121** |
| Porównanie numeryczne Python / TypeScript | **1000 / 1000** w tolerancji `1e-12` |
| Maksymalna różnica przyrostu informacji | `2.220446049250313e-16` |
| Pełne lokalne scenariusze CLI v1 | Python i TypeScript: T1 → obserwacja → T2, 4 commity, odrzucenie starej odpowiedzi |
| Pliki workflow YAML | **4 / 4** poprawnie sparsowane przez PyYAML 6.0.3 `BaseLoader` |
| Syntetyczna demonstracja v2 | 1 issue, 1 PR, 2 kandydatów, porażka → poprawka → sukces → `awaiting_merge` |
| Archiwum wydania | Budowa ZIP i SHA-256 na rzeczywistym lokalnym repozytorium; `.env` wykluczony, symlink odrzucony |

## Co było rzeczywiste, a co zastąpiono atrapą

**Rzeczywiste:** interpreter Pythona, Node.js, obliczenia obu silników, walidacja JSON, redakcja tekstu, kod kontrolera, lokalne obiekty Git, drzewa, commity i refy, optymistyczne uzgadnianie pamięci, pliki ZIP i sumy kontrolne, procesy testów.

**Atrapy:** sieciowe odpowiedzi GitHub API/`gh`, issues i PR-y na zdalnym serwerze, logi i wyniki Actions, odpowiedzi modelu językowego i funkcja `litellm.completion`. `tests_github/fakes.py` mapuje używane operacje Git Data API na rzeczywisty lokalny Git, ale obsługa HTTP/tokenów GitHub jest symulowana. Test warstwy uruchamiania `gh` sprawdza argumenty, stdin, błędy i `shell=False` przez zastąpienie procesu; nie uruchamia nieobecnego binarnego `gh`.

**Nie wykonano:** płatnego żądania OpenRouter, importu/instalacji prawdziwego LiteLLM, utworzenia issue/PR na koncie użytkownika, działania GitHub Actions na runnerze GitHub, zdalnego CD do Releases, weryfikacji reguł organizacyjnych/uprawnień, serwerowej walidacji składni wyrażeń Actions ani testu bezpieczeństwa izolacji runnera. Nie ma tutaj `actionlint` ani `gh`; LiteLLM także nie jest zainstalowany. Kontener nie miał połączenia sieciowego do instalacji zależności. Dokumentację providerów sprawdzono oddzielnym narzędziem przeglądania.

Workflow `CI` ma osobny job instalacji przypiętych zależności i importu SDK, wykonywany po umieszczeniu projektu na GitHub. To przygotowany test zdalny, **nie wynik testu wykonanego tutaj**. Bezpośrednie wersje są przypięte, lecz nie ma pełnego zweryfikowanego lockfile zależności przechodnich z hashami.

## Scenariusze objęte nowymi testami

Ścisłe kontrakty zadań i patchy; odrzucenie arbitralnego `score`, wymyślonych faktów, nieznanego profilu, starego SHA i błędnego hasha pliku; ograniczenie ścieżek, diffu, bajtów, symlinków i trybu wykonywalnego; brak powielania zadań przez parafrazy i issue po utracie odpowiedzi API; odtwarzanie przygotowanego commitu bez ponownego wywołania LLM; odmowa nadpisania zewnętrznej modyfikacji gałęzi.

Import run/attempt, redakcja logów i deduplikacja; metadane bez zmyślonych logów po ich wygaśnięciu; odrzucenie forka/nieznanego workflowu; odtwarzanie aktualizacji uczenia po przerwaniu między zapisem faktu a aktualizacją licznika; brak ponownego uczenia dla tej samej wersji kandydata; niezaliczanie anulowania, błędu setupu i samego zielonego testu przy nieudanym reporterze.

Rezerwacja dziennego limitu przed awarią modelu; odrzucenie nadmiernego kontekstu; brak powtarzania pustego planu przy identycznym kontekście; naprawione ponowienie nieskutecznego dispatch CI; ograniczenie liczby prób i obwód po kolejnych porażkach; auto-merge domyślnie wyłączony, odmowa bez ochrony, wymaganie dokładnego SHA i brak `--admin`.

Stałe przypięcia akcji, brak `pull_request_target`, oddzielny reporter, brak przekazywania kluczy LLM i GH do procesów kandydata, brak poświadczeń w checkoutach; pakowanie bez `.env`, sprawdzenie checksum i odrzucenie symlinków. Te testy sprawdzają określone własności implementacji, a nie dowodzą odporności na wszystkie ataki.

## Środowisko

| Narzędzie | Wersja / stan |
|---|---|
| Python | 3.13.5 |
| Node.js | 22.16.0; testy z `--experimental-strip-types` |
| Git | 2.47.3 |
| PyYAML (wyłącznie lokalna kontrola składni YAML) | 6.0.3 |
| python-dotenv lokalnie | 1.2.2; kontrakt ładowania `.env` testowany atrapą |
| LiteLLM | nie zainstalowano; kontrakt funkcji SDK testowany atrapą |
| GitHub CLI / actionlint | niedostępne w środowisku wykonania |

## Odtworzenie

```bash
python scripts/test_all.py
python scripts/demo_offline.py
```

Testy offline nie wymagają kluczy API ani instalacji LiteLLM. Potrzebują Pythona, Node.js i Git. Nowy sam kontroler można testować przez:

```bash
python -m unittest discover -s tests_github -p 'test_*.py' -v
```

Dowody: `tests/results/v2-full-tests.log`, `tests/results/v2-crosscheck.json`, `tests/results/v2-workflows.json`. Dane w `examples/github-offline/` są wyraźnie oznaczoną syntetyczną demonstracją. Pliki `tests/REPORT.md` i starsze logi bez prefiksu `v2-` pochodzą z poprzedniej wersji i są zachowane jako historia; bieżącym raportem jest ten dokument.

**Wniosek:** model i kontroler przechodzą opisane testy offline. Gotowość do pracy na konkretnym repozytorium wymaga pierwszego rzeczywistego smoke testu Actions/OpenRouter z ograniczonym kluczem i ręcznym scalaniem; niniejszy raport nie zastępuje tego kroku.
