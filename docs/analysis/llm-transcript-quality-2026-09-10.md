# Jakość odpowiedzi LLM na podstawie pełnych zapisów

```json
{
  "id": "llm-transcript-quality-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "b298ba4ef5da37ca24269d38b1f85dc0d7f90826",
  "evidence": [
    "benchmark/runs/20260910T120448Z-4012c1/manifest.json",
    "benchmark/runs/20260910T120448Z-4012c1/summary.json",
    "benchmark/runs/20260910T120448Z-4012c1/transcript-audit.json",
    "benchmark/runs/20260910T120448Z-4012c1/capture-verification.json",
    "benchmark/runs/20260910T120448Z-4012c1/edge-case-audit.json"
  ]
}
```

## Zapis i wynik

**Zakończono 27/27 iteracji. Zapisano i sprawdzono 33 requesty oraz 33 odpowiedzi SDK — 66 prywatnych plików JSON.**

| Rozwiązanie | Zielone etapy | Testy końcowe | Requesty / odpowiedzi | Błędy iteracji | Tokeny |
|---|---:|---:|---:|---:|---:|
| glm53 | 9/9 | 27/27 | 12 / 12 | 0 | 14448 |
| gpt6 | 8/9 | 27/27 | 9 / 9 | 1 | 9298 |
| opus5 | 9/9 | 27/27 | 12 / 12 | 0 | 12683 |

Łącznie 36 429 tokenów i 0,080937 USD według SDK. Wszystkie trzy rozwiązania końcowo naprawiły trzy projekty. GPT6 stracił jeden etap na błędną odpowiedź `{}`, po czym odzyskał wynik w kolejnej iteracji.

[Kontrola zapisu](../../benchmark/runs/20260910T120448Z-4012c1/capture-verification.json) potwierdziła kompletność, SHA-256, uprawnienia plików i brak znanych sekretów środowiskowych. Wszystkie istniejące w chwili startu źródła rozwiązań i benchmarku pozostały niezmienione podczas pomiaru.

Pełne wiadomości i odpowiedzi **tego przebiegu** znajdują się w prywatnym katalogu:

```text
.subactor/recovery/benchmark/20260910T120448Z-4012c1/<solution>/<project>/.bench/transcripts/
```

[Indeks receiptów](../../benchmark/runs/20260910T120448Z-4012c1/transcript-audit.json) wskazuje pliki i SHA-256. [Instrukcja](../information/benchmark-transcripts.md) opisuje format. Jest to pełne wejście i dostępne wyjście SDK LiteLLM po redakcji, nie zapis surowego HTTP ani ukrytego rozumowania niedostarczonego przez model. Starsze przebiegi nadal nie mają pełnych zapisów.

## Fakty ustalone z treści

### GLM53: błędna przesłanka w niewybranej propozycji

Wywołanie `glm53--invoice_math--001` zwróciło trzy propozycje. Kandydat `verify` twierdził, że `round(2.345, 2)` daje `2.34`, podczas gdy używany Python zwraca `2.35`. Błędna wypowiedź dotyczy przykładu działania istniejącej implementacji, nie samej zasady HALF_UP. Kandydat `derive`, przekazany w kolejnym requestcie do wykonania, zawierał poprawną diagnozę skali procentów i propozycję użycia Decimal. Kod przeszedł testy.

W odpowiedzi wykonania `glm53--job_queue--004` pojawił się dodatkowy opis po obiekcie JSON. Parser wyodrębnił obiekt i krok przeszedł, ale pełna odpowiedź nie była pojedynczym dokumentem JSON (11/12 odpowiedzi GLM53 spełniało ten warunek). Opis błędnie twierdził też, że `sorted(..., reverse=True)` odwraca kolejność elementów o równym kluczu; lokalna kontrola potwierdziła zachowanie stabilności.

**Wniosek:** zielone testy wybranej poprawki nie oznaczają, że wszystkie propozycje i uzasadnienia były prawdziwe. Sprawdzalne twierdzenia numeryczne warto zamieniać na kontrolowane przykłady testowe przed aktualizacją wiedzy. Nie traktować wyjścia proponującego LLM jako zwalidowanego faktu.

### GPT6: poprawny JSON, niepoprawny kontrakt i puste kryterium odbioru

Wywołanie `gpt6--url_router--001` zwróciło dokładnie `{}`, z `finish_reason=stop`. Walidator zgłosił `schema_fields at $: missing=['base_sha', 'tasks'], unexpected_count=0`. Request zawierał `response_format={"type":"json_object"}`; sam ten tryb nie gwarantuje wymaganych pól. To odtworzony błąd kontraktu, a nie ucięcie odpowiedzi. Benchmark używa adaptera i nie mierzy rodzimego odzyskiwania kontrolera w tej sytuacji.

Niezależnie, propozycja `gpt6--invoice_math--001` zawierała kryterium `acceptance_placeholder_2`. Nie występowało ono w requestcie. Walidator zaakceptował je jako niepusty tekst. Ten sam plan wprowadzał clamp do zakresu 0..100, który znalazł się w finalnym kodzie; zachowanie poza zadeklarowanym zakresem procentów nie zostało sprawdzone przez obecny oracle.

**Wniosek:** oprócz walidacji JSON potrzebna jest kontrola użyteczności kryteriów: odrzucenie placeholderów i powiązanie każdego kryterium z konkretnym zachowaniem/testem. Przy odpowiedzi `{}` zachować odrzucenie i ograniczone ponowienie; nie uzupełniać brakującego planu automatycznie. Zmian takich jak clamp nie uzasadniać wyłącznie ogólną chęcią „poprawy odporności” — powinny wynikać z kontraktu projektu.

### Opus5: propozycja poza zakresem oraz słabszy kontekst kodu

Wywołanie `opus5--invoice_math--001` zwróciło między innymi zadanie dodania `tests/test_invoice_math.py`, podczas gdy wykonawca benchmarku może zmieniać tylko `src/core.py`. Uzasadnienie określało granicę 100% jako nietestowaną, mimo że wejście zawierało nieudany test tej granicy. Istnienie nieudanego testu nie oznacza braku testu.

Request proponujący zadania zawierał cel i fakty o błędach CI, ale nie zawierał pełnego kodu `src/core.py` ani osobnej formalnej listy dozwolonych plików. Kod pojawia się dopiero przy wykonaniu. To cecha badanej kompozycji natywnego proponowania i adaptera, a nie dowód, że model miał te same informacje co konkurencyjne prompty.

W następnym planie `opus5--invoice_math--003` ponownie zaproponowano naprawę rabatu na podstawie błędu z iteracji 1, mimo że rabat był już naprawiony. Drugi kandydat postulował trzyargumentowe `taxed` i kwantyzację. To pozwala powiązać późniejsze rozszerzenie API z konkretną propozycją, a nie wyłącznie z wykonawcą.

**Wniosek:** wygaszać rozstrzygnięte fakty CI lub oznaczać je jako zastąpione nowszym wynikiem; przekazywać do generatora rzeczywisty inwentarz plików, zakres edycji i potrzebny kontekst kodu. Odrzucać niewykonalne zadania przed rankingiem. Oddzielić zadania ulepszania testów od napraw kodu ocenianych przez niezmienny zewnętrzny oracle.

## Dodatkowe przypadki brzegowe

[Dodatkowa kontrola](../../benchmark/runs/20260910T120448Z-4012c1/edge-case-audit.json) obejmuje po trzy nowe przypadki na każdy projekt, identyczne dla rozwiązań:

| Rozwiązanie | Dodatkowe testy wartości | Nieprzechodzące przypadki |
|---|---:|---|
| GLM53 | 8/9 | `query_value("na%6De=abc", "name")` zwraca `None` zamiast `"abc"` |
| GPT6 | 8/9 | `matches("/api/users", "/api/")` zwraca `False` zamiast `True` |
| Opus5 | 7/9 | Zakodowana nazwa parametru oraz `query_value("q=a%2Bb", "q")`: zwraca `"a b"` zamiast `"a+b"` |

Przypadki dodano **po obejrzeniu wyniku**, więc nie stanowią niezależnego, wcześniej zaplanowanego rankingu. Doprecyzowują obsługę końcowego `/` oraz dekodowania nazw parametrów. Wyniki oryginalnych 27 testów pozostają bez zmian. Błąd `%2B` pokazuje pomylenie zakodowanego plusa z plusem oznaczającym spację.

Dodatkowo Opus5 zmienił podpis `taxed(amount, percent)` na `taxed(amount, percent, tax_rate=None)`, wprowadził kwantyzację do centów i zwraca `Decimal`. Wartość `taxed(80,25)` jest numerycznie równa 100, dlatego dodatkowy test wartości przechodzi, lecz wynik nie jest serializowalny standardowym `json.dumps`. To zmiana zachowania API niewykrywana przez sam oracle porównujący liczby.

**Poprawki:** dodać testy dekodowania nazw i wartości osobno, `%2B`, prefiksów z końcowym `/`, typów zwracanych, serializacji i podpisów publicznych funkcji. Zakazać rozszerzania API i dodawania zaokrąglania bez odpowiedniego kryterium zadania. Nowe przypadki włączyć do następnego, z góry ustalonego zestawu testowego.


## Jak uczciwie porównywać jakość

Wspólne projekty i oracle zapewniają porównywalny cel naprawy, ale prompty nie są identyczne. GPT6 używa własnych kontraktów i temperatury 0.1, GLM53 dwóch trybów 0.8/0.2, a Opus5 0.7/0.2. Dostępny kontekst i liczba proponowanych zadań też się różnią. Seed benchmarku nie oznacza deterministycznej odpowiedzi endpointu: requesty nie muszą zawierać seeda modelu.

Raportować osobno:

1. **Kompletność kontraktu** — JSON, wymagane pola, dopuszczalne ścieżki, prawdziwe referencje.
2. **Jakość kandydatów** — prawdziwość diagnozy, wykonalność, konkretne kryteria i brak duplikatów.
3. **Jakość wyboru** — który kandydat został wybrany i czy inne dawały większą poprawę przy podobnym koszcie. Sama lektura niewykonanej propozycji nie dowodzi jej skuteczności.
4. **Jakość wykonania** — wynik widocznych i dodatkowych testów, regresje, zakres zmian oraz zachowanie publicznego API.
5. **Koszt i niezawodność** — wywołania, tokeny, opóźnienia, błędy transportu, schematu i wznowienia. Nie liczyć kroków bez wywołania LLM jako poprawnych odpowiedzi modelu.

Kolejny eksperyment powinien mieć ustalone z góry przypadki dodatkowe, kilka seedów/kolejności oraz dwa warianty: natywne prompty i wspólny zakres informacji wejściowej. Nie zmieniać jednocześnie kilku elementów, jeśli celem jest przypisanie poprawy konkretnemu mechanizmowi.

## Status

Wdrożono zapis, wykonano testy rejestratora i ponowny benchmark. Osiem testów infrastruktury benchmarku przeszło, w tym redakcja sekretów, uprawnienia plików, zachowanie niepoprawnego JSON i weryfikacja SHA-256. Nie publikowano pełnych treści do GitHub ani nie wykonywano zdalnych operacji Issue/PR/merge. Zmiany i raport są lokalne, bez commita.
