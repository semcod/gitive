# Testy rzeczywistych połączeń LLM i GitHub

```json
{
  "id": "live-project-tests-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "d3fd3409c75345b5c1e73934183c0cf8202bb096",
  "evidence": [
    {
      "project": "glm53",
      "private_receipt": ".subactor/recovery/runtime-tests/glm53.json",
      "sha256": "df8a16782dfa106aee29330734a2edd64e76fdb92639452642ab7b910f304539"
    },
    {
      "project": "opus5",
      "private_receipt": ".subactor/recovery/runtime-tests/opus5.json",
      "sha256": "e51e863020071867031c0885523f8f1c1e33e37910e693ebdf180ae9d904cde0"
    },
    {
      "project": "gpt6",
      "private_receipt": ".subactor/recovery/runtime-tests/gpt6.json",
      "sha256": "d1b0cdbdf6b841ef8bb540000702d9369b24a9579a3589c6a19fa81857ef7e72"
    }
  ]
}
```

## Wynik

Projekty uruchomiono kolejno: `glm53`, `opus5`, `gpt6`, z konfiguracją wspólnego
`gitive/.env`, rzeczywistym LiteLLM 1.83.0 i odczytami GitHub dla `semcod/gitive`.
Wszystkie trzy zakończyły opisany poniżej przebieg poprawnie.

| Projekt | Sprawdzony przebieg | Wynik | Czas |
|---|---|---|---|
| `glm53` | Synchronizacja 3 faktów CI, propozycja i wykonanie LLM, commit, replay | 4 nowe fakty, 1 krok replay, 4 commity w repo testowym | 36.49 s |
| `opus5` | 11 faktów git/CI/kodu, cel i propozycja LLM, ranking, podgląd issue | 1 propozycja issue; bez publikacji | 12.38 s |
| `gpt6` | Doctor, cykl tylko do odczytu oraz osobne rzeczywiste wywołanie adaptera LiteLLM | GitHub OK; JSON z polami edits/tasks, 174 tokeny łącznie | 3.26 s |

Wszystkie końcowe odpowiedzi LLM miały `finish_reason=stop`. Czasy obejmują końcowe
udane próby, bez wcześniejszej diagnostyki.

## Wykryte problemy i poprawki

Pierwotny identyfikator `openrouter/zai/glm-5.3` powodował HTTP 400 z informacją
`zai/glm-5.3 is not a valid model ID`. Katalog dostawcy wskazał `z-ai/glm-5.3`;
poprawiono wspólny `.env`, wartości domyślne, szablony oraz dokumentację.
Źródło identyfikatora: [katalog modeli OpenRouter](https://openrouter.ai/api/v1/models).

Pierwsza próba GLM53 po tej korekcie zwróciła brak treści odpowiedzi po około 100 s.
Nie zapisano wtedy powodu zakończenia, więc nie traktujemy wyczerpania tokenów jako
udowodnionej przyczyny. Dodano opcjonalny `LLM_REASONING_EFFORT`, ustawiono `low`
i powtórzono przebiegi z zapisem metadanych odpowiedzi. Wyniki były poprawne.
Adapter GLM53 rozpoznaje teraz `finish_reason=length` i zgłasza czytelny błąd limitu;
ten przypadek pokrywa nowy test regresyjny.

Bieżąca konfiguracja:

```dotenv
LLM_MODEL=openrouter/z-ai/glm-5.3
LLM_REASONING_EFFORT=low
OPENROUTER_API_KEY=<wartość istniejąca w prywatnym .env>
```

Model wspiera parametry reasoning; poziom wysiłku steruje jego pracą wewnętrzną.
[Opis parametrów reasoning OpenRouter](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

## Lokalne gh

Użyto istniejącej sesji `gh auth login`. Testowy proces pobierał istniejący token przez
`gh auth token --hostname github.com`, z przechwyceniem stdout w pamięci procesu,
i przekazywał go jako `GH_TOKEN` do komend potomnych. Nie tworzono nowego tokena,
nie wypisywano jego wartości i nie dopisywano go do `.env`.
Adaptery projektów same korzystają z lokalnego `gh`; przy działającej sesji logowania
ręczny eksport tokena nie jest potrzebny.

Powtórzenie kontroli GPT6 bez pobierania tokena do zmiennej:

```bash
cd /home/tom/github/semcod/gitive/gpt6
python3 -m intuition_github.cli --repo semcod/gitive doctor
python3 -m intuition_github.cli --repo semcod/gitive cycle
```

`doctor` i zwykły `cycle` nie wykonują wywołań LLM. Rzeczywiste wywołanie adaptera
LiteLLM w tym teście wykonano osobno, z minimalnym żądaniem JSON bez zmian repozytorium.

## Zakres i ograniczenia

Nie publikowano issues, PR, commitów ani statusów GitHub; nie wykonywano merge.
Pamięć GLM53 i Opus5 działała w katalogach tymczasowych. Wartość `created` w podglądzie
Opus5 oznacza wygenerowaną propozycję, nie issue utworzone na GitHubie.
Cykl GPT6 nie miał jeszcze zdalnej gałęzi pamięci (`memory_commit=null`) i wykrył dwa
kwalifikujące się uruchomienia CI. Nie sprawdzano przepływu `cycle --apply` ani wdrożenia
GitHub Actions. Powodzenie lokalnego klucza nie potwierdza poprawności sekretów Actions.

Surowe wyniki i skrypt testowy pozostają w ignorowanym `.subactor/recovery/runtime-tests/`.
Powyższe skróty wiążą raport z konkretnymi wynikami bez publikowania danych uwierzytelnienia.
Zmiany kodu i raport pozostają lokalne, bez commita ani PR.

## Regresje po poprawkach

- GLM53: 22 testy, wszystkie poprawne.
- GPT6: zestawy Python, TypeScript, crosscheck między językami oraz 71 testów kontrolera GitHub — poprawne.
- Opus5: 14/14 testów offline — poprawne.

Pierwsze `make test` zatrzymało się na domyślnym Node v20.19.5: brak opcji
`--experimental-strip-types`. Powtórzono `make test-gpt6 test-opus5` z istniejącym
Node v22.23.1 w PATH; kod wyjścia 0. GLM53 był już poprawnie sprawdzony w pierwszym przebiegu.
Nie zmieniano globalnej wersji Node. Dla powtórzenia pełnego zestawu użyj Node 22:

```bash
nvm use 22
make test
```

Potwierdzono też `gpt6 doctor` bez ręcznego ustawiania `GH_TOKEN`: lokalna sesja
`gh` wystarcza. Zaktualizowano paczkę `glm53/dist/glm53-intuition.tar.gz`.
