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
usterki obecne od początku. Grupy testów są ujawniane kumulatywnie: 3, 6 i 9 testów.
Wcześniejsze poprawki pozostają; błędy nie są sztucznie wstrzykiwane ponownie. Zielony
etap oznacza no-op bez wywołania modelu. Maksymalnie dwa wywołania LLM na iterację,
54 na cały przebieg, bez automatycznych retry. Błąd adaptera nie zatrzymuje innych par.

**Zakres porównania:** to pomiar natywnych komponentów z lokalnymi mostami wykonania,
nie pełnych wdrożeń GitHub. GLM53 i GPT6 korzystają z własnych planerów i walidatorów.
Opus5 ma własny planer, ale nie wykonuje natywnie patchy; benchmark dodaje mu jawnie
oznaczonego wykonawcę LLM. Nie należy przypisywać wyniku tej kompozycji samemu Opus5.
Trzy iteracje nie dowodzą poprawności nieskończonej pętli.

Pełna metodologia: [opis benchmarku](../docs/information/repair-benchmark.md).

## Zapisane przebiegi

- [20260910T104156Z-4580a6 — mock](runs/20260910T104156Z-4580a6/report.md)
- [20260910T104535Z-b48f5a — pilot](runs/20260910T104535Z-b48f5a/report.md)
- [20260910T104959Z-48c133 — live](runs/20260910T104959Z-48c133/report.md)
