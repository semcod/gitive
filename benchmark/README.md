# Benchmark trzech pętli napraw

Trzy rozwiązania × trzy lokalne projekty × trzy iteracje = **27 iteracji**.
Wykonanie jest sekwencyjne, z rzeczywistym GLM-5.3 przez LiteLLM i wspólnym `../.env`.
Każda para rozwiązanie–projekt ma własne repozytorium git oraz pamięć pomiędzy iteracjami.

```bash
# Z katalogu głównego gitive:
pip install -r benchmark/requirements.txt
python3 -m unittest discover -s benchmark/tests -v
python3 benchmark/run.py --mock  # tylko infrastruktura, bez LLM
python3 benchmark/run.py         # rzeczywiste 27 iteracji
```

Wymagana konfiguracja w `gitive/.env`:

```dotenv
OPENROUTER_API_KEY=<twoj-klucz>
LLM_MODEL=openrouter/z-ai/glm-5.3
LLM_REASONING_EFFORT=low
```

Każde wywołanie tworzy nowy katalog `benchmark/runs/<timestamp-UTC>-<suffix>/`:

- `report.md`: wyniki i ograniczenia interpretacji;
- `summary.json`, `iterations.csv`: agregaty i wszystkie iteracje;
- `manifest.json`: konfiguracja, commit rodzica oraz skróty SHA-256 kodu adapterów i rozwiązań;
- `iterations/`: wyniki przed i po naprawie, czasy, błędy, tokeny, statusy;
- `patches/`: rzeczywiste różnice kodu, również odrzucone;
- `final/`: końcowy kod i wynik pełnego zestawu testów.

[`latest.json`](latest.json) wskazuje ostatni ukończony przebieg oraz jego tryb.
Odczytaj `mode`: wynik `mock` nie mierzy skuteczności napraw. Raport jest odświeżany
po każdej parze rozwiązanie–projekt. Pojedyncze iteracje zapisują się natychmiast.
Repozytoria robocze, logi i pamięć zostają w ignorowanym `.subactor/recovery/benchmark/`.

Przykład krótszego przebiegu i ponownego wygenerowania raportu:

```bash
python3 benchmark/run.py --solutions glm53 --projects invoice_math --iterations 1
python3 benchmark/run.py --report benchmark/runs/<timestamp>
```

Projektami testowymi są `invoice_math`, `url_router` i `job_queue`. Każdy ma trzy
usterki obecne od początku. Grupy testów są ujawniane kumulatywnie. Wersja 2 obejmuje 13 przypadków
invoice_math, 12 url_router i 12 job_queue (37 na rozwiązanie); liczby są w manifeście.
Wcześniejsze poprawki pozostają; błędy nie są sztucznie wstrzykiwane ponownie. Zielony
etap oznacza no-op bez wywołania modelu. Maksymalnie dwa wywołania LLM na iterację,
54 na cały przebieg, bez retry transportu SDK. GLM53 może raz ponowić fazę przerwaną
przez `finish_reason=length`, w tym samym limicie wywołań. GPT6 może ponowić odrzucony patch w kolejnej iteracji,
zachowując zadanie i ten sam budżet. Błąd adaptera nie zatrzymuje innych par.

**Zakres porównania:** to pomiar natywnych komponentów z lokalnymi mostami wykonania,
nie pełnych wdrożeń GitHub. GLM53 i GPT6 korzystają z własnych planerów i walidatorów.
Od `execution_version=3` Opus5 wywołuje natywne `repair` w odizolowanym klonie Git.
Zewnętrzny oracle wymaga zielonego bieżącego etapu i braku nowych regresji;
pamięć wykonania jest zachowywana między iteracjami. Wynik natywnej operacji
znajduje się w `native_execution`. Jest to zmiana względem wcześniejszego mostu:
natywny executor odrzuca także częściową poprawę, jeśli etap nadal jest czerwony.
Przypadki pozostają identyczne (`fixture_version=2`); starszych wyników nie należy
traktować jako pomiaru nowej ścieżki wykonania. Klon Git nie jest sandboxem systemowym.
Trzy iteracje nie dowodzą poprawności nieskończonej pętli.

Pełna metodologia: [opis benchmarku](../docs/information/repair-benchmark.md).

## Zapisane przebiegi

- [20260910T104156Z-4580a6 — mock](runs/20260910T104156Z-4580a6/report.md)
- [20260910T104535Z-b48f5a — pilot](runs/20260910T104535Z-b48f5a/report.md)
- [20260910T104959Z-48c133 — live](runs/20260910T104959Z-48c133/report.md)

Pełne zapisy nowych wywołań LLM: [instrukcja](../docs/information/benchmark-transcripts.md). Analiza receiptów: `python3 benchmark/analyze_transcripts.py benchmark/runs/IDENTYFIKATOR`.

Wyniki poprawek i porównanie na identycznych przypadkach v2: [raport jakości](../docs/analysis/quality-fixes-v2-2026-09-10.md).
