# Pełne zapisy wywołań LLM w benchmarku

```json
{
  "id": "benchmark-transcripts",
  "kind": "information",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "b298ba4ef5da37ca24269d38b1f85dc0d7f90826",
  "evidence": ["benchmark/transcripts.py", "benchmark/tests/test_transcripts.py"]
}
```

## Zakres

Przebiegi uruchamiane po dodaniu `transcript_capture=redacted-sdk-request-response-v1`
w manifeście zapisują każde wywołanie LiteLLM. Poprzednich przebiegów nie uzupełniono:
ich brakujących odpowiedzi nie można odtworzyć.

Rejestrowane są:

- pełne wiadomości system/user i kontekst kodu przekazany do `litellm.completion`;
- model, temperatura, limity, format odpowiedzi, reasoning_effort oraz inne obsługiwane parametry generacji;
- wszystkie pola udostępnione przez `ModelResponse.model_dump`, w tym choices, treść, dostępne pola reasoning, usage i finish_reason;
- dostępna diagnostyka nieudanego wywołania, czas oraz metryki kosztu SDK;
- identyfikator rozwiązania, projektu, iteracji i wywołania.

To zapis **wejścia i wyjścia SDK**, nie przechwycenie surowych bajtów HTTP. Nie zapisuje
wewnętrznych przekształceń LiteLLM, nagłówków, kluczy API ani treści niewysłanej przez
dostawcę. Pole reasoning jest dostępne tylko wtedy, gdy dostawca je zwrócił.

## Przechowywanie

Pełne treści znajdują się poza śledzonymi plikami Git:

```text
.subactor/recovery/benchmark/<run>/<solution>/<project>/.bench/transcripts/
  <solution>--<project>--001.request.json
  <solution>--<project>--001.response.json
  <solution>--<project>--001.error.json  # tylko gdy wystąpi błąd
```

Katalog ma uprawnienia 0700, pliki 0600. Zapis żądania następuje przed wywołaniem
modelu; odpowiedź jest zapisywana przed walidacją JSON przez rozwiązanie. Dzięki temu
można przeanalizować również odpowiedź uciętą albo odrzuconą przez parser. Pliki są
zapisywane atomowo; istniejący identyfikator nie może zostać nadpisany.

Dane są redagowane: pomijane są pola uwierzytelniania i nagłówki, znane sekrety ze
środowiska oraz rozpoznawalne formaty kluczy zastępuje `[REDACTED]`. Pełne treści
pozostają prywatne także po redakcji; filtr nie jest gwarancją wykrycia każdego
potencjalnie poufnego fragmentu dowolnego projektu.

## Odczyt i weryfikacja

Każda metryka `llm_calls` w `benchmark/runs/<run>/iterations/*.json` zawiera
`request_receipt`, `response_receipt` lub `error_receipt`. Receipt wskazuje ścieżkę
względem głównego katalogu projektu, SHA-256 zapisanych bajtów i ich liczbę.

```bash
python3 benchmark/run.py
python3 benchmark/analyze_transcripts.py benchmark/runs/IDENTYFIKATOR
```

Druga komenda sprawdza skróty i tworzy `transcript-audit.json`: długości promptów,
kształt JSON, liczbę propozycji/edycji, fazy i powiązanie z wynikiem iteracji. Nie
kopiuje pełnych wiadomości do publicznego raportu. Ocena sensowności propozycji wymaga
lektury pełnych treści; poprawny JSON sam w sobie nie dowodzi jakości naprawy.

Prywatny katalog należy zachować razem z receiptami. Sam raport bez tego katalogu
nie pozwoli odczytać wiadomości i odpowiedzi.
