# Benchmark lokalnych pętli napraw

```json
{
  "id": "repair-benchmark",
  "kind": "information",
  "version": 2,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "working tree based on d3fd340; exact content hashes recorded per run",
  "evidence": ["benchmark/run.py", "benchmark/worker.py", "benchmark/adapters.py", "benchmark/tests/"]
}
```

## Cel

Zmierzyć trzy kroki pracy nad naprawami w trzech kontrolowanych projektach dla każdego
z rozwiązań GLM53, GPT6 oraz Opus5. Użytkownik wybrał projekty lokalne i raportowanie
w katalogu `benchmark`; timestampowane raporty znajdują się zatem w
`benchmark/runs/<timestamp>/report.md`, a ten dokument opisuje stałą metodologię.

## Przebieg

Kolejność: GLM53 dla wszystkich projektów, GPT6 dla wszystkich projektów, Opus5 dla
wszystkich projektów. Projekty: kalkulator rozliczeń, router URL, kolejka zadań.
Trzy iteracje na parę dają łącznie 27 rekordów. Każda para startuje z identycznego
kodu projektu, w nowym repozytorium git. Pozostają zarówno patche, jak i stan nauki.

Wszystkie usterki są obecne w kodzie startowym. Oracle ujawnia grupy testów stopniowo,
aby symulować nowe obserwacje CI bez ponownego psucia poprawionego kodu. Etapy obejmują
3, 6 i 9 testów, zachowując poprzednie wymagania. Pełny oracle działa poza repozytorium
edytowanym przez model. Do modelu trafiają tylko obecnie ujawnione niepowodzenia.
Wyniki zmiennoprzecinkowe porównywane są z tolerancją względną i bezwzględną 1e-9.

Planer rozwiązania wybiera zadanie. Patch może zmienić wyłącznie istniejący
`src/core.py`, musi mieć poprawną składnię Python i mieścić się w limicie rozmiaru.
Natywne walidatory mogą nałożyć dodatkowe ograniczenia. Testy weryfikują patch; gate
akceptuje go, gdy poprawia liczbę zaliczonych testów bieżącego etapu i nie powoduje
nowej regresji w pełnym oracle. W przeciwnym razie kod zostaje przywrócony. Następuje
zapis wyniku i informacji zwrotnej do adaptera. Już zielony etap nie wywołuje LLM.

## Granice natywności

| Rozwiązanie | Używane natywne komponenty | Część dodana przez benchmark |
|---|---|---|
| GLM53 | `choose`, `Client`, `PATCH`, `validate_edits`, `persist` | Lokalny oracle, obsługa napraw czerwonego projektu bez GitHub |
| GPT6 | `LiteLLMClient`, `validate_tasks`, `score`, `validate_patch`, stan startowy | Transport lokalny, feedback Beta według gate zamiast uruchomień GitHub, wyłączenie czasowego cooldownu |
| Opus5 | `cycle`, cechy napięcia/tarcia, scorer, `complete`, `update_theta` | Lokalny transport faktów, predefiniowany cel, wykonawca patcha, feedback według gate |

GPT6 nie uruchamia tutaj pełnego `Controller.cycle`, publikacji issues/PR ani weryfikacji
zaufanych checków. Opus5 w wersji natywnej proponuje zadania; wykonawca pochodzi z benchmarku.
Wynik Opus5 należy zawsze opisywać jako **Opus5 + wykonawca benchmarku**. Lokalny feedback
w GPT6/Opus5 wykorzystuje autentyczny wynik testów, ale inną semantykę niż produkcyjne
zaakceptowanie PR/issue. GLM53 nadal nagradza nową obserwację, również negatywną.

## Pomiary i odtwarzanie

Każdy rekord zawiera status, wynik testów przed/po, wykryte regresje, zaakceptowanie
patcha, hashe kodu i commitów, czas oraz metadane wywołań. Tokeny pochodzą z odpowiedzi
SDK. Ceny są podawane wyłącznie, jeśli SDK dostarczy koszt; nieznane wartości pozostają
`null`. Błędy bez usage nie oznaczają zerowego rachunku. Limit wynosi 2 wywołania na
iterację, 6 na parę, timeout 120 s na wywołanie, bez retry. Wcześniejsze testy oracle,
inicjalizacja repo i importy nie wchodzą do sumy czasów iteracji.

Manifest zawiera model, reasoning effort, seed, bazowy commit i hashe faktycznie
używanych źródeł. Wywołania zdalnego LLM nie są deterministyczne mimo identycznego seeda.
Nie losujemy kolejności rozwiązań; to ograniczenie pomiaru czasu i cache dostawcy.
Jedna próba na parę i niewielkie projekty nie uzasadniają uogólnień statystycznych.

Repozytoria robocze nie są usuwane, dzięki czemu można przejrzeć git log i stan pamięci.
`--report` odtwarza prezentację z zapisanych rekordów bez wywołań LLM. Ponowne normalne
uruchomienie tworzy osobny timestamp i świeże repozytoria; nie dopisuje do starego raportu.

## Uruchomienie i status

Instrukcja: [benchmark/README.md](../../benchmark/README.md).
Wyniki: [wskaźnik ostatniego przebiegu](../../benchmark/latest.json).

Kod jest wykonywany w osobnym procesie bez kluczy w środowisku i z osobnym HOME;
nie jest to izolacja systemowa. Przeznaczenie: wybrane kontrolowane projekty testowe.
Benchmark nie używa zdalnego GitHub i nie tworzy issues, PR ani zdalnych commitów.
Trzy iteracje to skończona próba pętli napraw, nie dowód jej niezawodności bez końca.

## Kontrola pilotażowa

Przebieg `20260910T104535Z-b48f5a` zachowano jako pilotażowy. Ujawnił on, że most GPT6
używał uproszczonych nazw pól promptu. Zastąpiono je dokładnym zestawem pól i nazwami
celów `propose_tasks`/`propose_patch` z oryginalnego kontrolera. Test kontraktu sprawdza
teraz te nazwy. Projekty, testy i kryteria przyjmowania poprawek pozostały takie same;
porównanie końcowe korzysta z nowego pełnego przebiegu. Nie interpretujemy pilota jako
rankingu rozwiązań.
