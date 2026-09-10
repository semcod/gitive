# Intuition GitHub 2.0

Konfiguracja LLM: wspólny `../.env` w workspace (`gitive/.env`),
`OPENROUTER_API_KEY`, `LLM_MODEL=openrouter/z-ai/glm-5.3` oraz
`LLM_REASONING_EFFORT=low`, przez LiteLLM.
Po przeniesieniu projektu osobno używany jest lokalny `.env`.

**Logi CI/CD → fakty w Git → zadanie → GitHub Issue → poprawka LLM → PR → izolowany job testów → kolejne fakty.**

Kontroler działa w Pythonie, używa `gh` jako jedynego interfejsu do GitHub i LiteLLM SDK do połączenia z OpenRouter. Pamięć to osobna gałąź Git — bez bazy danych, serwera agenta, kolejki zewnętrznej i wektorowego magazynu. Zachowano wcześniejsze implementacje matematyczne w Pythonie i TypeScript oraz ich testy porównawcze.

To implementacja referencyjna do uruchomienia i oceny w wydzielonym repozytorium. **Nie jest deklaracją sprawdzenia prawdziwego konta GitHub, wszystkich dostawców OpenRouter ani autonomicznej poprawności kodu.** Zakres wykonanych testów: [docs/TEST-REPORT.md](docs/TEST-REPORT.md).

## Co rzeczywiście robi projekt

| Element | Implementacja |
|---|---|
| Fakty z CI i CD | Metadane uruchomienia, próba, SHA, wyniki jobów, URL i oczyszczony fragment logu pobierany przez `gh run view --attempt ... --log`. |
| Pamięć | Gałąź `intuition-memory`, `state.json`, zdarzenia `events/`, dowody `evidence/`; obiekty Git tworzone przez `gh api`. |
| Propozycje | LiteLLM/OpenRouter zwraca JSON z odwołaniami do istniejących faktów i plików. Kontroler waliduje i oblicza priorytet. |
| Tickety | `gh issue create`, stabilny identyfikator w treści, uzasadnienie, źródła, kryteria odbioru i etykieta `intuition:managed`. |
| Poprawki | LLM proponuje pełną nową zawartość małej liczby istniejących plików; kontroler sprawdza hash starej wersji i zakres zmian. |
| Pull requesty | Commit i gałąź przez Git Data API, PR przez `gh pr create`; nigdy bezpośredni push poprawki do `main`. |
| Weryfikacja | `gh workflow run verify-candidate.yml` z dokładnym numerem PR i SHA; osobny job bez przekazanego klucza LLM i tokenu zapisu. |
| Wynik | Zaufany reporter publikuje status `Intuition / verified` dla sprawdzonego SHA; nowy cykl pobiera logi. |
| CD | Pakiet źródeł ZIP i SHA-256 trafiają do GitHub Releases jako prerelease; nie oznacza to wdrożenia na serwer produkcyjny. |
| Ciągłość | Zdarzenia `workflow_run`, ręczny dispatch i harmonogram co 6 godzin; każdy cykl ma skończony budżet. |

**Pętla nie musi wymyślić nowej zmiany.** Brak uzasadnienia, brak budżetu, kolejka pełna, oczekiwanie na scalenie lub awaria wstrzymują generowanie.

## 1. Uruchomienie lokalne

Wymagania: Python 3.11+ (workflow używa 3.13), Git, GitHub CLI `gh`; do obu zestawów regresji również Node.js 22.16+ z obsługą `--experimental-strip-types`. Kontroler nie wymaga Node.js. Instrukcje `gh` poniżej wykonuje operator po zalogowaniu do swojego konta.

```bash
cd intuition-github
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

gh auth login
# Pobierana paczka zawiera także pusty .env. Odtworzenie szablonu:
cp .env.example .env
```

Uzupełnij lokalnie `.env`:

```dotenv
GITHUB_REPOSITORY=OWNER/REPOSITORY
GH_TOKEN=
OPENROUTER_API_KEY=TU_WSTAW_KLUCZ_LOKALNIE
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/openai/gpt-4.1-mini
OR_SITE_URL=https://github.com
OR_APP_NAME=Intuition-GitHub
LLM_TIMEOUT_SECONDS=120
LLM_JSON_MODE=true
INTUITION_ENABLED=false
INTUITION_AUTOMERGE=false
```

Puste `GH_TOKEN` pozwala korzystać z logowania `gh`; można też podać token o odpowiednich uprawnieniach. Model jest konfigurowalnym przykładem, nie wynikiem benchmarku. Prefiks LiteLLM to `openrouter/`, po nim identyfikator modelu OpenRouter [S1]. Obsługa JSON i limity wybranego modelu muszą odpowiadać ustawieniom. Dla modelu bez `response_format` ustaw `LLM_JSON_MODE=false`; ścisła walidacja odpowiedzi pozostaje aktywna.

`.env` jest ignorowany przez Git i wykluczany z wydań CD. Ładowanie przez `python-dotenv` nie zastępuje istniejących zmiennych środowiskowych i nie wykonuje poleceń powłoki.

```bash
# Żadnych zmian i żadnego wywołania LLM:
python -m intuition_github.cli doctor
python -m intuition_github.cli cycle
python -m intuition_github.cli status

# Testy offline, bez gh i bez SDK/providerów:
python scripts/test_all.py

# Syntetyczny obieg issue -> PR -> błąd -> poprawka -> sukces, bez API:
python scripts/demo_offline.py
```

Aby lokalnie wykonać rzeczywisty cykl, ustaw w `.env` `INTUITION_ENABLED=true`, a następnie:

```bash
python -m intuition_github.cli cycle --apply
```

**To polecenie wysyła wybrane źródła i oczyszczone fragmenty logów do OpenRouter, może zużyć płatne tokeny oraz tworzy commity pamięci, issues i PR-y.** Nie uruchamiaj lokalnego cyklu równolegle z cyklem Actions: sprawdzanie refów odrzuci konflikt, ale procesy nie mają wspólnej blokady poza Git.

## 2. Umieszczenie w nowym repozytorium

Najpierw przejrzyj kod, zakres plików, limity i [SECURITY.md](SECURITY.md). Zacznij od prywatnego repozytorium testowego, nie od kodu z sekretami czy danymi klientów.

```bash
git init -b main
git add .
git status --short
# .env NIE powinien wystąpić w staged files.
git commit -m "Add evidence-backed GitHub refactoring loop"
gh repo create intuition-github --private --source=. --remote=origin --push
```

Dla istniejącego repozytorium skopiuj pliki bez nadpisywania własnych workflowów w ciemno. Dostosuj `allowed_paths`, nazwy workflowów oraz stałe polecenia testowe. Agent nie wykonuje poleceń odczytanych z issue lub logu.

W ustawieniach repozytorium GitHub włącz Issues i Actions, zezwól wybranym przypiętym akcjom na wykonanie oraz w **Settings → Actions → General → Workflow permissions** dopuść tworzenie PR-ów przez Actions. Polityki organizacji mogą blokować te uprawnienia. Nie nadawaj tokenowi prawa obchodzenia ochrony głównej gałęzi.

## 3. Secrets i Variables w GitHub Actions

`.env` działa lokalnie. Actions korzysta z Secrets/Variables, nie z klucza zapisanego w repozytorium.

```bash
# Polecenie poprosi o sekret — nie wklejaj go do historii komend.
gh secret set OPENROUTER_API_KEY

gh variable set OPENROUTER_MODEL --body 'openrouter/openai/gpt-4.1-mini'
gh variable set INTUITION_AUTOMERGE --body false
gh variable set INTUITION_CD_ENABLED --body true

# Najpierw inspekcja bez wywołania modelu:
gh workflow run intuition-loop.yml --ref main --raw-field dry_run=true
gh run list --workflow intuition-loop.yml

# Włączenie cyklicznych zapisów i płatnych żądań:
gh variable set INTUITION_ENABLED --body true
gh workflow run intuition-loop.yml --ref main --raw-field dry_run=false
```

Własną gałąź domyślną podstaw zamiast `main`. Pliki workflowów muszą znajdować się w gałęzi domyślnej [S3].

Domyślnie kontroler używa krótkotrwałego `GITHUB_TOKEN` przekazanego jako `GH_TOKEN`. W jobie kontrolera ustawiono `contents`, `issues`, `pull-requests`, `actions` i `statuses` na `write`; job wykonujący propozycję ma wyłącznie `contents: read` i nie dostaje sekretów aplikacyjnych.

Opcjonalny secret `INTUITION_GH_TOKEN` zastępuje token kontrolera. Dla fine-grained PAT ogranicz go do jednego repozytorium i wymaganych operacji: Contents, Issues, Pull requests, Actions, Commit statuses. Odczyt klasycznej ochrony gałęzi dla auto-merge może dodatkowo wymagać Administration: read. Nie potrzebuje prawa modyfikowania workflowów. Adapter nie zawiera automatycznego odnawiania tokenu GitHub App; PAT wygasa zgodnie ze swoją konfiguracją. Zwykle wystarcza token wbudowany, bez dodatkowego PAT.

### Dlaczego jawne uruchomienie testów?

GitHub ogranicza zdarzenia wywołane przez `GITHUB_TOKEN`. Według dokumentacji sprawdzonej 10.09.2026 `workflow_dispatch` i `repository_dispatch` tworzą uruchomienia; zdarzenia PR `opened`, `synchronize`, `reopened` mogą utworzyć uruchomienia wymagające zatwierdzenia, a wiele innych zdarzeń nie uruchomi kolejnego workflowu [S2]. Dlatego kontroler nie polega na samym `gh pr create`: wywołuje osobny zaufany weryfikator dla dokładnego SHA. Analogicznie uzgadnia brak CI po scaleniu.

## 4. Workflowy

| Plik | Wyzwalanie | Działanie |
|---|---|---|
| `ci.yml` | push, PR, dispatch | Testy Python/TypeScript oraz — poza PR — instalacja i import SDK bez żądania API. |
| `intuition-loop.yml` | zakończenie CI/CD/weryfikacji, cron, dispatch | Fakty, budżet, ranking, issues, commity i PR-y. |
| `verify-candidate.yml` | jawny dispatch | Sprawdzenie tożsamości PR, test dokładnego SHA, publikacja zaufanego statusu. |
| `cd.yml` | udany CI gałęzi domyślnej | Budowa ZIP, suma kontrolna, prerelease w GitHub Releases. |

Harmonogram `17 */6 * * *` oznacza 00:17, 06:17, 12:17, 18:17 **UTC**, nie stałą godzinę w Warszawie. Opóźnienia, pomijanie zdarzeń przy obciążeniu, limity konta oraz wyłączenie harmonogramu publicznego nieaktywnego repozytorium po 60 dniach wykluczają gwarancję literalnej nieskończoności [S3]. Nie ma stale pracującego procesu `while True`; zasoby nie są zajmowane podczas oczekiwania.

`workflow_run` ma ograniczenie długości łańcucha i jest zdarzeniem uprzywilejowanym. Sterownik uruchamia oddzielny workflow przez dispatch, a harmonogram uzgadnia stan po utraconych zdarzeniach. Nigdy nie uruchamia źródeł z PR w jobie mającym klucz OpenRouter [S3].

## 5. Zakres, limity i koszt

Zaufana konfiguracja: `.intuition/config.json`. Domyślnie agent może zmieniać tylko istniejące zwykłe pliki:

```json
["demo_app/*.py", "python/engine.py", "typescript/engine.ts"]
```

| Ograniczenie | Wartość domyślna |
|---|---:|
| Wywołania LLM na dzień UTC | 8 |
| Wywołania LLM na cykl | 2 |
| Nowe issues na cykl | 1 |
| Otwarte zarządzane issues | 4 |
| Otwarte PR-y agenta | 1 |
| Próby poprawki na issue | 2 |
| Kolejne negatywne wyniki testów przed blokadą | 3 |
| Zmieniane pliki na poprawkę | 3 |
| Dodane + usunięte linie na poprawkę | 250 |
| Rozmiar jednego pliku | 64 000 bajtów |
| Odpowiedź modelu | maksymalnie 4096 tokenów |
| Żądanie modelu | maksymalnie 100 000 znaków po serializacji wraz z instrukcją |
| Fragment logów przechowywany jako dowód | około 16 000 znaków |
| Nowe uruchomienia importowane na cykl | 6 |

Limity żądań rezerwowane są w Git **przed** wywołaniem LLM. Timeout lub odrzucenie odpowiedzi nie oddają wykorzystanej rezerwacji. Automatyczne retry SDK są wyłączone. Fakty w kontekście i kod są osobno przycinane, a niecały log trafia do promptu.

To nie jest twardy limit dolarowy: ceny modeli, tokenizacja, żądania zakończone timeoutem i współdzielenie klucza mogą zmienić koszt. Ustaw niezależny limit kredytów konkretnego klucza w OpenRouter oraz limity wydatków/minut/storage GitHub [S7]. Stan w Git nie obejmuje użycia tego klucza przez inne aplikacje.

Wyczerpanie budżetu dobowego nie blokuje następnego dnia. `needs_human` i przerwanie po kolejnych awariach są celowe; samo ponowienie nie może zastępować diagnozy. Repozytorium i historia dowodów także mają ograniczony rozmiar. Stan jest kompaktowany, ale pełna historia i pliki zdarzeń rosną; archiwizacja pozostaje zadaniem operatora.

## 6. Ręczne scalenie i opcjonalny auto-merge

**Domyślnie zielony PR czeka na opiekuna.** Zapis `awaiting_merge` oznacza zakończoną weryfikację kandydata, nie wdrożenie. Po scaleniu kolejny cykl pobiera nowy stan gałęzi domyślnej i kontynuuje pracę.

Opcja `INTUITION_AUTOMERGE=true` jest zaimplementowana, lecz działa tylko po spełnieniu jawnych warunków: repozytorium pozwala na auto-merge, klasyczna ochrona głównej gałęzi jest strict, wymaga `Intuition / verified`, obejmuje administratorów, zabrania force-push; dla dokładnego SHA istnieje pomyślny status. Kontroler wywołuje `gh pr merge --auto --squash --match-head-commit ...`, nigdy `--admin`, i nie obchodzi wymaganych recenzji. Brak praw odczytu ochrony, same rulesets bez odpowiadającej im klasycznej ochrony lub brak statusu pozostawiają PR do decyzji człowieka. **Nie jest to bezwarunkowe automatyczne scalanie.**

Uwaga przy włączaniu tego statusu jako wymaganego w istniejącym projekcie: klasyczna reguła dotyczy także PR-ów ludzi. Dostarczony weryfikator obsługuje tylko ograniczone gałęzie i pliki agenta; normalny pipeline PR-ów musi otrzymać własnego, zaufanego wydawcę równoważnego statusu lub wymagana jest odrębna organizacja reguł. Nie włączaj globalnego wymogu bez zaplanowania ścieżki aktualizacji kontrolera i zwykłych PR-ów. Wersja domyślna z ręcznym scalaniem nie potrzebuje tego rozszerzenia. [S8]

## 7. Obsługa, diagnostyka i wyłączenie

```bash
gh issue list --label 'intuition:managed'
gh pr list
gh run list --workflow verify-candidate.yml
python -m intuition_github.cli status

# Historyczny run (numer bierzesz z Actions; dane są pobierane przez gh):
python -m intuition_github.cli cycle --apply --run-id 123456789

# Pamięć bez przełączania bieżącego drzewa roboczego:
git fetch origin intuition-memory
git show origin/intuition-memory:state.json

# Reset obwodu po analizie problemu; nie kasuje historii ani limitów kosztowych:
gh workflow run intuition-loop.yml --ref main \
  --raw-field dry_run=false --raw-field reset_circuit=true

# Wstrzymanie nowych zapisów agenta i nowych publikacji CD:
gh variable set INTUITION_ENABLED --body false
gh variable set INTUITION_CD_ENABLED --body false
# Już uruchomione joby anuluj osobno:
# gh run cancel NUMER_URUCHOMIENIA
```

Reset obwodu nie wznawia samoczynnie ticketów `needs_human`, nie zmienia reguł ochrony i nie zeruje dziennego budżetu. Obejrzyj issue/PR, popraw konfigurację ręcznie, zamknij/rozstrzygnij konflikt. Edycja komentarza w issue nie wydaje agentowi nowego polecenia.

Typowe problemy:

| Objaw | Znaczenie / działanie |
|---|---|
| `Resource not accessible by integration` | Sprawdź ograniczenia organizacji, uprawnienia joba/tokena i zgodę na tworzenie PR-ów. |
| PR jest, zwykły CI czeka na zgodę | Sprawdź osobny `Verify candidate`; nie zakładaj, że zdarzenie PR uruchomi CI bez zatwierdzenia. |
| Brak nowych zadań | Możliwe: identyczny kontekst, brak uzasadnienia, próg wyniku, otwarty PR, limit issues lub konserwatywna deduplikacja. |
| Błąd OpenRouter / brak JSON | Sprawdź model, saldo, dostęp, `LLM_JSON_MODE`; nie podnoś limitu prób bez diagnozy. |
| Log wygasł | Fakt metadanych pozostaje; agent nie dopisuje zmyślonej treści brakującego logu. |
| Konflikt gałęzi lub zmienione SHA | Kontroler odmawia nadpisywania; sprawdź równoległą pracę ludzi/innego agenta. |
| Zielony test, nieudany reporter | Nie jest zaliczany jako zaufana pozytywna weryfikacja. |
| Brak CD | Potrzebne `INTUITION_CD_ENABLED=true`, udany CI własnej gałęzi domyślnej i uprawnienia Releases. |
| Limit wielkości/paginacji GitHub | Agent zatrzymuje się zamiast planować na niepełnym stanie; zarchiwizuj repo/dowody i dostosuj obsługę skali. |

## 8. Struktura

```text
.github/workflows/         CI, cykl, weryfikator, CD
.intuition/config.json     polityka i limity kontrolera
.env.example, .env         pusty szablon i lokalne ustawienia (bez klucza w paczce)
intuition_github/          kontroler, gh, LiteLLM, fakty, pamięć i kontrakty
scripts/                   stałe testy, budowanie i publikacja wydania
python/, typescript/       oryginalne modele referencyjne i CLI v1
demo_app/                  mały przykładowy cel zmian
tests_github/              nowe testy offline, w tym rzeczywiste lokalne obiekty Git
docs/                      architektura, model CI/CD, wyniki testów, źródła
MODEL.md                   matematyka v1 (zachowana)
SECURITY.md                model zagrożeń i ograniczenia
```

Dokumentacja: [architektura](docs/ARCHITECTURE.md), [model CI/CD](docs/CI-MODEL.md), [testy](docs/TEST-REPORT.md), [źródła S1–S8](docs/SOURCES.md). Repozytorium v1 znajdziesz funkcjonalnie w `python/` i `typescript/`, a jego wcześniejszą instrukcję w `docs/README-v1.md`.

### Odzyskiwanie po błędnej propozycji

Błędy kontraktu propozycji są zapisywane w pamięci jako `plan_failure`.
Następny cykl ponawia próbę z diagnostyką, do `max_attempts_per_issue` dla tego
samego kontekstu, w granicach istniejących budżetów. Zużycie otrzymanej odpowiedzi
jest rozliczane także przy błędzie parsowania. Dla `openrouter/z-ai/glm-5.3`
ścisły schemat odpowiedzi jest domyślnie włączony, wraz z routingiem
`provider.require_parameters=true`. `LLM_JSON_SCHEMA=false` wyłącza ten tryb;
dla innych modeli wymaga on jawnego `LLM_JSON_SCHEMA=true` i wsparcia endpointu.
Lokalne kontrole SHA, zakresu i sygnatur API pozostają obowiązkowe.

### Tożsamość weryfikacji i niezmienne wydania

`resolve-candidate` zwraca również `merge_sha` i `test_profile_digest`. Reporter
wymaga `--base`, `--merge`, `--profile` z tej samej fazy resolve. Zmiana bazy,
HEAD, wyniku połączenia lub profilu blokuje przyjęcie starego sukcesu.
Szablon workflow testuje dokładny commit połączenia. Przed żądaniem automerge
kontroler sprawdza skrót tej tożsamości w statusie.

Pakowanie tworzy `release-manifest.json` obok ZIP i `SHA256SUMS.txt`.
Publikator sprawdza pełny SHA taga i bajty wszystkich plików; konflikt kończy
operację bez nadpisania. Powtórzenie uzupełnia brakujące pliki i weryfikuje
opublikowaną zawartość. Wynik `release_verified` nie oznacza instalacji aplikacji
ani wdrożenia na serwerze. Konfiguracja niezależnego Validatora pozostaje wymagana.

Stan wdrożenia i testy: [audyt autonomii](../docs/analysis/autonomous-delivery-2026-09-10.md).
