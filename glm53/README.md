# GLM53 — intuicja, LLM i pamięć w git

Kompletny projekt Python 3.11+: generator zadań z krytykiem, fakty append-only,
uczenie online, replay historii, logi CI jako fakty oraz generowanie i naprawianie PR.
Bez bazy danych. Rdzeń i testy używają standardowej biblioteki; LiteLLM jest opcjonalne.

```bash
cd glm53
python3 -m unittest discover -s tests -v
python3 -m intuition --help
./pack.sh
```

Uruchomienie demonstracji w tym katalogu:

```bash
git init -b main
git config user.name "Twoje imię"
git config user.email "twoj-email@example.com"
git add .
git commit -m "Initialize GLM53 project"
python3 -m intuition init "Teoria grafów: jakie własności warto zbadać?"
python3 -m intuition --backend mock run --steps 3
python3 -m intuition replay
```

Tryb `mock` generuje obserwacje demonstracyjne, bez połączeń sieciowych.
Model i dane robocze powstają przy `init` w `state.json`, `facts/` i `log/tasks.jsonl`.
Wymagana jest skonfigurowana tożsamość git oraz czyste repozytorium.

[Pełna instrukcja, konfiguracja i ograniczenia](docs/information/glm53-guide.md) ·
[Indeks dokumentacji](docs/README.md)

Paczka: `dist/glm53-intuition.tar.gz`. Zawiera kod, testy, workflow i dokumentację;
nie zawiera kluczy, lokalnej historii ani danych eksperymentów.
