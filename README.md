# gitive

Trzy niezależne implementacje tego samego pomysłu: systemu, który zbiera fakty
z repozytorium i CI, proponuje zadania z użyciem LLM oraz wykorzystuje wynik
tych zadań do kolejnych decyzji. Każdy katalog przedstawia wariant wykonany z
pomocą innego modelu językowego.

| Katalog | Model | Implementacja |
| --- | --- | --- |
| [`glm53/`](glm53/) | GLM-5.3 | Samodzielny pakiet Python z trwałą pamięcią Git, krytykiem uczącym się, obsługą faktów CI i mechanizmem bezpiecznego refaktoryzowania. |
| [`gpt6/`](gpt6/) | GPT-6 | Miejsce na wariant implementacji przygotowany przez GPT-6. Katalog zachowuje ten sam kontrakt funkcjonalny co pozostałe warianty. |
| [`opus5/`](opus5/) | Opus 5 | Pakiet `intuition`, który traktuje generowanie zadań jako amortyzowane wnioskowanie na podstawie historii Git, logów CI i markerów w kodzie. |

## Wspólny cel

Każdy wariant ma realizować tę samą pętlę:

1. obserwować historię Git, wyniki CI i sygnały z kodu;
2. zapisać fakty oraz określić bieżące napięcie między stanem projektu a celem;
3. wygenerować i uszeregować propozycje zadań przez LLM;
4. wykorzystać zamknięte zadania i wyniki CI jako sygnał zwrotny dla kolejnej iteracji.

Katalogi są celowo rozdzielone, aby można było porównywać decyzje projektowe,
zależności, testy i zachowanie implementacji pochodzących od różnych modeli.

## Uruchamianie

Główny `Makefile` uruchamia dostępne testy wariantów:

```bash
make test
```

Dokładne instrukcje konfiguracji każdego wariantu są w jego własnym katalogu.
