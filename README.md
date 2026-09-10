# gitive

`gitive` porównuje trzy niezależne implementacje pętli „intuicji” dla repozytorium: system zbiera obserwacje z historii Git i CI, utrwala je jako fakty, prosi LLM o propozycje działań, a następnie uczy się na ich wynikach. Każdy podkatalog jest samodzielnym wariantem z inną architekturą i zestawem testów.

| Wariant | Model | Podejście | Testy lokalne |
| --- | --- | --- | --- |
| [`glm53/`](glm53/) | GLM-5.3 | Python bez obowiązkowych zależności zewnętrznych; pamięć i fakty append-only w Git, krytyk uczony online oraz kontrolowane tworzenie i naprawianie PR. | `make -C glm53 test` |
| [`gpt6/`](gpt6/) | GPT-6 | Kontroler GitHub-native z gałęzią pamięci, LiteLLM/OpenRouter, issues, PR, osobnym workflow weryfikacji i porównawczymi modelami Python/TypeScript. | `python3 gpt6/scripts/test_all.py` |
| [`opus5/`](opus5/) | Opus 5 | Pakiet `intuition`: amortyzowane wnioskowanie z historii Git, logów CI i markerów w kodzie, z rankingiem kandydatów i sprzężeniem zwrotnym. | `python3 opus5/tools/offline_test_runner.py` |

## Wspólny przepływ

```text
Git + CI + kod → fakty i stan → propozycje LLM → walidacja i ranking
                       ↑                              ↓
                       └──── wynik zadania / CI ──────┘
```

Warianty różnią się zakresem automatyzacji, a nie wspólnym celem. `glm53` koncentruje się na lekkim, lokalnym rdzeniu i bezpiecznej obsłudze zmian; `gpt6` obejmuje pełniejszą integrację GitHub, weryfikację dokładnego SHA i publikację wydania; `opus5` skupia się na modelu rankingu opartym na napięciu między celem a bieżącym stanem projektu.

## Uruchamianie

Przed uruchomieniem wariantu przeczytaj jego README i nie zapisuj kluczy w repozytorium. Główny Makefile uruchamia dostępne testy offline:

```bash
make test
```

Szczegóły, ograniczenia i dowody weryfikacji są w [indeksie dokumentacji](docs/README.md).
