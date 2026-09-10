# Poprawki jakości i benchmark wersji 2

```json
{
  "id": "quality-fixes-v2-2026-09-10",
  "kind": "analysis",
  "version": 2,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "b298ba4ef5da37ca24269d38b1f85dc0d7f90826",
  "evidence": [
    "benchmark/runs/20260910T125348Z-quality-refactor/verification.json",
    "benchmark/runs/20260910T122228Z-3e2b37/manifest.json",
    "benchmark/runs/20260910T122228Z-3e2b37/summary.json",
    "benchmark/runs/20260910T123602Z-51ced9/summary.json",
    "benchmark/runs/20260910T123602Z-51ced9/verification.json",
    "glm53/tests/test_quality.py",
    "gpt6/tests_github/test_contracts.py",
    "opus5/tests/test_quality.py",
    "benchmark/tests/test_benchmark.py"
  ]
}
```

## Aktualizacja refaktoryzacji — wersja dokumentu 2

Wdrożono punkty 1–3 z sekcji „Następne poprawki”. Historyczne wyniki live poniżej pozostają wynikami poprzednich wersji; ta aktualizacja jest potwierdzona testami offline, bez nowych wywołań dostawcy LLM.

- **GLM53:** osobny `TruncatedResponse` uruchamia najwyżej jedno ponowienie tej samej fazy. Każde wywołanie zużywa istniejący budżet. Drugie ucięcie kończy próbę; inne błędy nie uruchamiają tej ścieżki. Kontekst JSON jest kompaktowany, historia i lista faktów ograniczane, a kod źródłowy i wymagany kontrakt pozostają kompletne. Gdy nie ma zbędnej historii, skrócenie kontekstu może być niewielkie. Telemetria zachowuje osobne zdarzenia, a recorder benchmarku zapisuje każde wywołanie przed parsowaniem, również niekompletne odpowiedzi.
- **GPT6:** walidator rozróżnia błąd składni od zmiany publicznego API; diagnostyka podaje liczbę usuniętych, dodanych i zmienionych sygnatur oraz wymaganie zachowania oryginalnego kontraktu. Kontroler zapisuje `patch_rejection` w trwałej pamięci, przekazuje je jako `previous_rejection` przy kolejnej próbie i usuwa po poprawnej walidacji. Lokalny adapter stosuje to samo przekazywanie informacji. Komunikat jest redagowany i ograniczony do 1000 znaków.
- **Opus5:** regularny benchmark wywołuje natywne `repair` zamiast własnego promptu i walidatora patchy. Natywny kod zarządza klonem, testami, kontrolą API, wycofaniem i nagrodą wykonania. Zewnętrzny klon oddziela jego commity od bramki benchmarku, a `.bench/native-repair` zachowuje pamięć wykonania między iteracjami. Wynik jest raportowany jako `native_execution`. Nie wywołuje się zdalnego GitHub.

**Metodologia:** `execution_version=3`, nadal `fixture_version=2` (37 przypadków). Opus5 wymaga pełnego sukcesu aktualnego etapu; częściowa poprawa nie wystarcza do przyjęcia przez jego natywny executor. Tej zmiany nie ukryto w starych raportach i nie przeliczono ich jako wyniku nowej implementacji.

Punkt 4 dotyczy niezależnego wdrażania. Wcześniejsza aktualizacja [audytu autonomii](autonomous-delivery-2026-09-10.md) dodała w GPT6 powiązanie wyniku z aktualną krotką SHA i kontrolę niezmiennych wydań. Wdrożenie chronionego Validatora oraz pełna integracja zdalnych ścieżek GLM53 i Opus5 pozostają otwarte. Ta refaktoryzacja nie włącza automerge ani publikacji.

Weryfikacja: GLM53 28 testów, GPT6 GitHub 87, benchmark 10 oraz dodatkowy test wycofania regresji Opus5 — wszystkie przeszły. Test GPT6 potwierdza zachowanie diagnostyki po odtworzeniu kontrolera z pamięci Git. Testy adapterów wykonują rzeczywiste lokalne operacje Git i oracle, z atrapą SDK. `compileall` i `git diff --check` przeszły. [Wyniki i skróty źródeł](../../benchmark/runs/20260910T125348Z-quality-refactor/verification.json).

Bazowa rewizja tej aktualizacji: `9bf5c8618de5b1b1cf7edf93a27394298999381e`. Zmiany i dokumentacja są lokalne, bez nowego commita lub PR.

## Historia implementacji i benchmarku v2

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
- Adapter zachowuje historię faktów, lecz do planowania kolejnego etapu przekazuje bieżący wynik testów. Odrzucony patch jest ponawiany z istniejącym zadaniem w następnej iteracji.
- Dla `openrouter/z-ai/glm-5.3` domyślnie włączono ścisły JSON Schema z aktualnym SHA i `provider.require_parameters=true`; `LLM_JSON_SCHEMA=false` pozwala wyłączyć ten tryb. Routing wymaga endpointu obsługującego parametry zgodnie z [dokumentacją OpenRouter](https://openrouter.ai/docs/guides/features/structured-outputs). Schemat nie zastępuje testów semantyki.

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

Wszystkie końcowe repozytoria przechodzą **37/37** identycznych testów v2. GLM53 i Opus5 pochodzą z [przebiegu v2](../../benchmark/runs/20260910T122228Z-3e2b37/report.md), GPT6 z [powtórki po korekcie adaptera](../../benchmark/runs/20260910T123602Z-51ced9/report.md). Nie jest to jeden wspólny przebieg po ostatniej zmianie.

| Rozwiązanie | Końcowe testy | Zielone etapy / 9 | Wywołania LLM | Tokeny | Koszt USD |
|---|---:|---:|---:|---:|---:|
| GLM53 | 37/37 | 5/9 | 17 | 30 443 | 0.085844 |
| GPT6, powtórka | 37/37 | 8/9 | 13 | 15 541 | 0.032612 |
| Opus5 | 37/37 | 9/9 | 8 | 9 606 | 0.021823 |

Pierwszy przebieg ujawnił błąd lokalnego adaptera GPT6: odrzucony patch pozostawiał identyfikator zadania przy niezmienionym SHA, blokując ponowną propozycję. Wynik diagnostyczny wynosił 20/37. Adapter teraz zachowuje zadanie i ponawia patch w kolejnej iteracji, bez przekroczenia budżetu. Ten przypadek ma test regresji. Powtórka obejmowała od początku wszystkie trzy projekty i dziewięć iteracji GPT6.

GLM53 miał dwa błędy odpowiedzi LLM i jedną odrzuconą regresję; końcowo odzyskał poprawność w trzecich iteracjach. GPT6 w powtórce miał jeden patch odrzucony przez kontrolę API, po czym skutecznie ponowił zadanie. Opus5 nie miał odrzuconych zmian w tym przebiegu. Jedna próba nie pozwala ustalić trwałego rankingu kosztów czy niezawodności.

Dla porównania archiwalne końcowe pliki z poprzedniego przebiegu ponownie oceniono tym samym oracle v2, bez LLM: GLM53 36/37, GPT6 36/37, Opus5 30/37 ([dane](../../benchmark/runs/20260910T122228Z-3e2b37/baseline-v2-recheck.json)). To porównanie konkretnych artefaktów, nie kontrolowana estymacja wpływu każdej zmiany.

## Weryfikacja i ograniczenia

Przeszedł pełny `make test`: GLM53 27 testów; GPT6 Python 25, TypeScript 25, kontrola zgodności i GitHub 76; Opus5 20; benchmark 9. Po korekcie ponawiania ponownie przeszły testy GitHub (77) i benchmarku (10). Po dodaniu testu domyślnego schematu przeszły wszystkie 33 testy kontraktów GPT6. `compileall` i `git diff --check` przeszły.

Osobny `make test-native-repair` zastosował zapisane patche przez natywne executory GLM53 i Opus5: po 37/37 przypadków. Było to odtworzenie, bez kolejnych wywołań LLM.

Audyt potwierdził SHA-256 zapisów wszystkich **52 requestów i 52 odpowiedzi SDK**: 39 wywołań przebiegu diagnostycznego i 13 powtórki GPT6. Pliki są prywatne (0600), klucze i nagłówki autoryzacji są wyłączone lub redagowane. To zapis argumentów LiteLLM i obiektu ModelResponse, nie surowych pakietów HTTP. Po zmianach GPT6 i adaptera skróty pierwszego przebiegu naturalnie różnią się od bieżącego kodu; [weryfikacja](../../benchmark/runs/20260910T123602Z-51ced9/verification.json) jawnie wykazuje te różnice.

Benchmark zachowuje pełny prywatny zapis requestów i odpowiedzi LiteLLM, z receiptami i SHA-256. Wersja przypadków oraz skróty źródeł są zapisane w manifeście. Testy symulujące SDK są oddzielone od przebiegu live.

Nadal jest to lokalne porównanie komponentów i adapterów wykonania, nie test produkcyjnego Issue → PR → merge → release. Nie zmieniano reguł GitHub, nie tworzono zdalnych zgłoszeń, PR ani tagów. Zmiany pozostają lokalne, bez commita.

## Następne poprawki dla autonomicznego wdrażania

1. GLM53: po `finish_reason=length` ponawiać tylko przerwaną fazę, z ograniczonym budżetem i krótszym kontekstem; zachować odpowiedź diagnostyczną. W tym przebiegu błędy LLM obniżyły skuteczność etapów mimo końcowego sukcesu.
2. GPT6: przekazywać w ponowieniu dokładny powód odrzucenia API, nie tylko bieżące błędy testów. Schemat JSON rozwiązuje strukturę odpowiedzi, lecz nie chroni semantyki patcha.
3. Opus5: przenieść do regularnego benchmarku bezpośrednie wywołanie natywnego `repair`, aby zmniejszyć różnice między lokalnym mostem a ścieżką produkcyjną.
4. Dla wszystkich: przed automatycznym merge niezależnie weryfikować aktualne SHA gałęzi bazowej i PR, wymagane checks oraz zgodność artefaktu wydania z niezmiennym tagiem. Konkretne wcześniej odtworzone luki opisuje [audyt dostarczania](autonomous-delivery-2026-09-10.md). Ten benchmark ich nie zamyka i nie potwierdza produkcyjnego cyklu Issue → PR → merge → tag.
