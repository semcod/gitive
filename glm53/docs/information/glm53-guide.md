# GLM53: instrukcja i model wykonania

```json
{
  "id": "glm53-guide",
  "kind": "information",
  "version": 2,
  "date": "2026-09-10",
  "owner": "glm53",
  "status": "local",
  "source_revision": "local-uncommitted-1.0.0",
  "evidence": ["tests/test_model.py", "tests/test_integration.py", "tests/test_transport.py"]
}
```

## Cel i zakres

Projekt implementuje opis użytkownika w Pythonie. Wariant TypeScript nie jest
potrzebny do uruchomienia. Katalog `glm53` jest samodzielnym projektem: aby workflow
zadziałały, jego zawartość musi stanowić katalog główny docelowego repozytorium.
GitHub nie uruchamia workflow znajdujących się w `glm53/.github` wewnątrz większego repo.

Dwie ścieżki wykonania:

1. `run`: propozycja → krytyk → wybór → nowe fakty → walidacja → commit i uczenie.
2. `refactor`: propozycja nad wiedzą i kodem → kontrolowany patch → testy w klonie →
   podgląd albo issue, branch i PR. `repair` aktualizuje ten sam PR po błędzie CI.

## Instalacja

Wymagania: Python ≥3.11, git CLI; dla integracji GitHub dodatkowo `gh`.
Testy i backend HTTP nie wymagają pakietów pip.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[llm]'
cp .env.example .env
```

`pip install -e .` instaluje sam rdzeń i polecenie `intuition`.
Zakresy zależności są w `pyproject.toml` i `requirements.txt`; projekt nie dostarcza
zamrożonego zestawu zależności przechodnich LiteLLM.

Jeżeli projekt nie ma historii, wykonaj polecenia git z README. Istniejące pliki
projektu trzeba najpierw świadomie zapisać w commicie. Program nie wykonuje `git add -A`.

```bash
python3 -m intuition init 'Teza: graf bez cykli jest lasem' --tau 0.35 --m 5 --eta 0.01
python3 -m intuition --backend mock run --steps 3
python3 -m intuition status
python3 -m intuition replay
```

`init` odmawia nadpisania istniejącej pamięci. Opcje globalne `--root` i `--backend`
umieszczaj przed komendą. `--root` umożliwia prowadzenie pamięci w innym repozytorium.
Program odrzuca podkatalog repozytorium jako root, aby nie commitować zmian rodzica.

## LLM

LiteLLM i OpenRouter, konfiguracja `.env`:

```dotenv
LLM_BACKEND=litellm
LLM_MODEL=openrouter/zai/glm-5.3
OPENROUTER_API_KEY=<twoj-klucz>
LLM_TIMEOUT=180
LLM_MAX_TOKENS=4096
```

Wstaw identyfikator modelu dostępnego na swoim koncie. Prefiks `openrouter/` jest
formatem LiteLLM. [Dokumentacja dostawcy LiteLLM](https://docs.litellm.ai/docs/providers/openrouter).

Endpoint zgodny z OpenAI, np. lokalny serwer:

```dotenv
LLM_BACKEND=compatible
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=<lokalny-model>
LLM_API_KEY=
```

HTTP używa `/chat/completions`; nie wymaga SDK OpenAI. Backend LiteLLM również
obsługuje `LLM_BASE_URL` jako `api_base`. W tym workspace wspólny `gitive/.env` jest ładowany przez wszystkie projekty.
Po przeniesieniu projektu osobno używany jest `.env` z `--root`. Wyeksportowane
zmienne środowiskowe mają pierwszeństwo. Domyślny backend to LiteLLM.

```bash
python3 -m intuition run --steps 5
python3 -m intuition run --dry-run
```

`--dry-run` wywołuje propozycję LLM i krytyka, lecz nie wykonuje zadania ani nie zapisuje
pamięci. Zapytanie do zewnętrznego LLM może być płatne. Niepoprawny JSON, transport lub
schemat propozycji kończy polecenie błędem, bez fałszywej nagrody zero. Poprawna tablica
wykonania bez zaakceptowanych faktów daje rzeczywistą nagrodę zero.

## Model matematyczny i jego granice

`embed` używa BLAKE2b o skrócie 8 bajtów, 256 wymiarów, unigramów i bigramów
polskich/łacińskich tokenów długości co najmniej 3. Normalizacja L2 pozwala liczyć
cosinus iloczynem skalarnym. Metoda jest deterministyczna, lecz nie jest semantycznym
modelem embeddingowym; podobieństwo nie dowodzi prawdziwości ani równoważności zdań.

Krytyk liczy:

- `nov`: 1 minus średnia podobieństw do maksymalnie 5 najbliższych faktów;
- `coh`: log-mean-exp podobieństw z β=8, stabilny numerycznie;
- `grn`: udział unikalnych referencji występujących w bazie;
- `val`: próbka Beta dla archetypu, współdzielona przez jego kandydatów w danym kroku.

Użyteczność to `w · feats`, wybór to softmax `U/tau`. Przy `tau=0` wybór jest
zachłanny z losowaniem między remisami. Kandydaci są próbką propozycji LLM:
nie znamy liczbowo g_LLM i nie mnożymy softmaxa przez wymyślone prawdopodobieństwa.
Temperatura propozycji wynosi 0.8, wykonania/patcha 0.2.

Nagroda to liczba nowych faktów przechodzących schemat i deduplikację: cosinus musi
być **mniejszy niż 0.95**, także wobec wcześniejszych elementów tej samej odpowiedzi.
Jest to walidacja struktury i nowości, a nie zewnętrzne potwierdzenie prawdy. Pytania
`open` i hipotezy również są rekordami wiedzy. Refaktoryzacja dodaje obserwację wyniku
realnie uruchomionych testów, a nie zapewnienie LLM o ich powodzeniu. Wynik testu
negatywnego też może dostarczyć nową obserwację i dodatnią nagrodę informacyjną.

Aktualizacja: `alpha[a] += reward`, `beta[a] += int(reward == 0)`. Opcjonalne `eta>0`
włącza wykładniczą aktualizację nieujemnych wag z gradientu błędu kwadratowego.
Eksponent jest ograniczony do [-50, 50], wagi do 1e6 dla stabilności numerycznej.
Domyślne `eta=0` pozostawia wagi stałe.

Nie deklarujemy gwarancji regret O(d√T): liniowy scorer z heurystycznym Beta-bandytą
archetypów nie jest pełnym algorytmem liniowego kontekstowego Thompson samplingu,
a nagroda jest liczbą faktów, nie pojedynczą obserwacją Bernoulliego. `nov+coh` jest
heurystyką ciekawości; kod nie estymuje entropii ani rzeczywistego EIG.

Seed zapewnia odtwarzalne losowanie krytyka przy takich samych kandydatach i stanie.
Nie gwarantuje deterministyczności zdalnego LLM. W logu zachowywani są wszyscy kandydaci,
cechy, prawdopodobieństwa, seed, stan przed/po i commit rodzica.

## Pamięć i transakcje

```text
facts/*.json        jeden niezmienny fakt na plik, także ci_*.json
log/tasks.jsonl     trajektoria append-only
state.json          aktualne alpha, beta, w, tau, m, eta, step, wersja embeddingu
```

Fakt ma `id`, `content`, `tags`, `references`, `source`, `created` i opcjonalnie
`supersedes`, `metadata`. Korekta jest nowym rekordem. `supersedes` usuwa poprzednie
otwarte pytanie z aktywnego frontu, ale nie usuwa go z pamięci. Front obejmuje także
referencje do nieistniejących identyfikatorów. Uszkodzone pliki powodują błąd.

Pojedynczy commit pamięci obejmuje nowe fakty, wiersz trajektorii i zaktualizowany stan.
Fakty są numerowane od maksymalnego istniejącego numeru, a nie od liczby plików.
Commit kodu refaktoryzacji poprzedza commit obserwacji testów na tej samej gałęzi PR.

Blokada `.intuition.lock` zapobiega równoczesnym procesom w jednym checkoutcie.
Dziennik `.intuition-pending.json` i atomowa zamiana plików umożliwiają odzyskanie
przerwanej transakcji. Błąd commita przywraca tylko pliki tej transakcji.
Po awarii sprawdź PID w blokadzie; gdy proces już nie działa, usuń wyłącznie tę
nieaktywną blokadę i wykonaj `python3 -m intuition recover`. Program odmawia
nadpisania zmian wykonanych po awarii. Dziennika nie usuwaj przed odzyskaniem.

`replay` kontroluje niezmienność blobów faktów w całej historii first-parent,
append-only trajektorii i odtwarza aktualizacje wag/Beta. Nie powtarza wywołań LLM.
Rozgałęzione eksperymenty można porównywać poprzez raporty replay na ich gałęziach;
automatyczny konsensus/merge rozbieżnych stanów krytyka nie jest zaimplementowany.

## Refaktoryzacja i GitHub

Najpierw skonfiguruj `gh auth login` i `gh auth setup-git`, repo `owner/repo`, remote
oraz bazową gałąź `main`. Konfiguracja użytkownika git musi być dostępna lokalnie.

Podgląd offline na przykładowym pliku:

```bash
python3 -m intuition --backend mock refactor --repo owner/repo --allow examples \
  --test '["python3","-B","-c","from examples.demo import add; assert add(2,3)==5"]'
```

Podgląd prawdziwego LLM, a następnie publikacja:

```bash
python3 -m intuition refactor --repo owner/repo --allow intuition
python3 -m intuition refactor --repo owner/repo --allow intuition --publish
python3 -m intuition repair 123 --repo owner/repo --allow intuition
python3 -m intuition auto-merge 123 --repo owner/repo
```

Bez `--publish` zwracany jest JSON zawierający diff i wynik testów. Kolejne wywołanie
z `--publish` generuje nową propozycję; podgląd nie jest przechowywanym planem zatwierdzenia.
`repair` jawnie aktualizuje zdalny PR. `auto-merge` wymaga niepustego zestawu pozytywnych
checków i zgodności SHA; włącza mechanizm GitHub z zachowaniem reguł repozytorium.
[Opcje merge](https://cli.github.com/manual/gh_pr_merge),
[statusy checków i kody wyjścia](https://cli.github.com/manual/gh_pr_checks).
Merge na gałęzi domyślnej zamyka powiązane issue dzięki `Fixes #N`.

LLM może edytować 1–5 istniejących, śledzonych plików kodu z katalogów `--allow`.
Testy, ukryte katalogi, pamięć, pliki binarne i ścieżki spoza przekazanego kontekstu
są wyłączone. Obsługiwane rozszerzenia: py, ts, js, tsx, jsx, go, rs, java.
Kontekst kodu jest ograniczony do 100 tys. znaków. Dodawanie/usuwanie plików przez LLM
nie należy do tej wersji protokołu patcha.

Komenda testowa jest tablicą argv, bez interpretacji przez shell. Nowy PR wymaga
przechodzącej bazy i przechodzącej zmiany. Naprawa istniejącego czerwonego PR nie wymaga
zielonej bazy. Klon tymczasowy chroni bieżący checkout, ale **nie jest sandboxem OS**:
testy wykonują kod z dostępem użytkownika i siecią. Sekrety API/tokeny nie są przekazywane
w środowisku procesu testów; używaj izolowanego runnera dla niezaufanego kodu.

Issue/push/PR to niezależne operacje zewnętrzne, bez wspólnej transakcji. Jeśli publikacja
przerwie się po utworzeniu issue lub pushu, sprawdź issue i gałąź `intuition/issue-N`;
nie uruchamiaj ślepo kolejnego publikowania. Istniejący otwarty PR intuicji ogranicza WIP
do jednego. Nieudane testy nowej propozycji zapisują lokalną obserwację, bez publikacji
wadliwego kodu. Odmówiony/zamknięty PR nie zasila automatycznie modelu na gałęzi bazowej;
jego trajektoria pozostaje na gałęzi PR. Nagroda mierzy wiedzę z testów, nie akceptację PR.

## Synchronizacja CI i automatyczny cykl

```bash
python3 -m intuition sync-ci --repo owner/repo --limit 20
```

Pobierane są ukończone uruchomienia Actions. Id faktu zawiera skrót repo, run id i numer
próby, więc ponowienie synchronizacji jest idempotentne. Nowa próba tworzy nowy fakt,
a wcześniejszą oznacza przez `supersedes`. Logi błędów są obcinane do ostatnich 100 linii
oraz 12 tys. znaków; znane klucze środowiska i nagłówki Authorization są redagowane.
Redakcja nie rozpoznaje wszystkich możliwych sekretów zawartych w dowolnym tekście.
Limit obejmuje ostatnią stronę uruchomień (1–100), nie historyczny backfill całego repo.
Sukces innego run id nie zamyka automatycznie wszystkich wcześniejszych błędów.

Workflow `continuous-intuition.yml` uruchamia jeden ograniczony cykl co 6 godzin lub
ręcznie. Nie ma triggera push, który generowałby samonapędzającą się serię publikacji.
Przed włączeniem:

1. Zainicjalizuj i wypchnij projekt oraz pamięć na `main`.
2. Ustaw `LLM_MODEL` w Repository Variables i `OPENROUTER_API_KEY` w Secrets.
3. Ustaw sekret `INTUITION_TOKEN`: fine-grained PAT lub dostarczany token instalacyjny
   GitHub App z prawami Contents, Issues, Pull requests: write oraz Actions: read.
   Krótkotrwały token App wymaga własnego kroku jego uzyskania/odświeżania w workflow.
4. Ustaw `INTUITION_ENABLED=true`. Opcjonalne `INTUITION_AUTO_MERGE=true` uruchamia
   auto-merge po checkach; skonfiguruj wymagane recenzje i statusy zgodnie z polityką repo.

Domyślny GITHUB_TOKEN nie uruchamia kolejnego workflow przez zwykły push/PR, dlatego
publikacja używa osobnego tokena. [Reguła GitHub dotycząca triggerów](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Otwarty bot PR jest sprawdzany w następnym cyklu: pending → czekanie, failure → naprawa,
success → oczekiwanie na merge lub opcjonalny auto-merge. Bez otwartego PR: synchronizacja
CI i nowa propozycja. Dane CI trafiają do PR razem z kodem; jeśli kod nie zostanie
opublikowany, workflow próbuje zachować nową pamięć w osobnym PR `intuition/memory-*`.
Taki PR pamięci wymaga rozstrzygnięcia przez operatora. Workflow nie pushuje wprost na main.

Dostarczony CI to szablon GitHub Actions z macierzą Python 3.11/3.12/3.13 na Linux.
Nie jest dowodem wdrożenia chronionych checków ani lokalnego Validator/OneDev.
W środowisku z niezależnym walidatorem zachowaj jego reguły publikacji i pozostaw
`INTUITION_AUTO_MERGE` wyłączone, jeśli merge należy do tego walidatora.

## Weryfikacja i paczka

```bash
make check
./pack.sh
tar -tzf dist/glm53-intuition.tar.gz
```

Testy obejmują wzory krytyka, temperaturę, schematy, deduplikację, front, uczenie,
blokady, rollback commita, replay, idempotencję CI, rzeczywisty serwer HTTP kompatybilny,
refaktoryzację w klonie oraz publikację/naprawę przez lokalny bare remote i atrapę gh.
Nie wykonują płatnych wywołań LLM ani operacji na prawdziwym GitHubie.

Archiwum tworzone jest z jawnej listy plików projektu; pomija dane, `.git`, `.env`,
cache i dowiązania. Rozpakowanie daje katalog `glm53/`. Nie ma fikcyjnego URL pobierania;
gotowy plik jest w `dist/` i może zostać opublikowany przez właściciela projektu.

## Dalszy rozwój

Możliwe rozszerzenia: semantyczne osadzenia zapisane z wersją modelu, estymacja EIG,
uczenie z rozstrzygnięć odrzuconych PR, import pełnej historii CI, sandbox kontenerowy,
cache zatwierdzanych patchy i automatyczny konsensus gałęzi. Nie są przedstawiane jako
funkcje już wdrożone.
