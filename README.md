# Gitive

Gitive łączy benchmark trzech rozwiązań do naprawy kodu, panel WWW, CLI i istniejący pulpit noVNC z ekosystemu Subactor. Pozwala dodawać projekty do developmentu, wybierać rozwiązanie według benchmarku oraz tworzyć prywatne kopie projektów i profili z PC.

Kod aplikacji znajduje się w **[`src/gitive/`](src/gitive/)**. Silniki `glm53`, `gpt6` i `opus5` pozostają osobnymi komponentami repozytorium. Ich nazwy identyfikują implementacje — model wywoływany przez LLM określa konfiguracja `.env`.

## Architektura i realizacja projektów

Gitive jest zarządcą workspace, projektów i procesów. Workspace opisuje **środowisko**
(kontener, runtime, profile i prywatne dane), projekt opisuje **produkt w Git**,
a ticket jest jednostką pracy z celem, testami i powiązaniem z Issue/PR.
GLM53/GPT6/Opus5 są wykonawcami wybieranymi według benchmarku.

- [Architektura, struktury katalogów i cykl projektu](docs/information/workspace-project-architecture.md)
- [Etapy implementacji, migracja i kryteria odbioru](docs/refactoring/workspace-delivery.md)
- [Schematy danych](src/gitive/contracts/) i [szablony](src/gitive/templates/)

Docelowo projekt przechodzi: **workspace → ticket → Issue → branch → implementacja
→ testy konkretnego SHA → PR → kontrolowany merge → opcjonalny tag/release**.
Kod pozostaje w repo projektu; konfiguracja środowiska i prywatne dane należą do
workspace. Tickety są w `project/` zgodnie z zasadami danego repo, a wykonawca nie
może sam zastąpić niezależnej weryfikacji przed publikacją.

Dostarczone schematy i szablony są przygotowaniem nowego modelu. Pełny import runtime,
kontenery per projekt i nowy egzekutor ticketów **nie są jeszcze wdrożone**.
Bieżące komendy poniżej opisują obecny, węższy zakres kopiowania.

## Struktura

```text
src/gitive/          # pakiet: CLI, serwer, panel, workspace i integracja noVNC
  tests/            # testy aplikacji
  vendor/           # zależność Subactor wraz z manifestem integralności
  contracts/        # schematy workspace, projektu i ticketu
  templates/        # wzorce środowisk control/browser/project i struktury projektu
  Dockerfile
  compose.yaml
glm53/              # pierwszy silnik napraw
gpt6/               # drugi silnik napraw
opus5/              # trzeci silnik napraw
benchmark/          # wspólne przykłady, wykonanie i raporty po timestamp
  runs/
docs/               # dokumentacja, analizy i zapisy weryfikacji
pyproject.toml      # instalowalny pakiet i entry point gitive
gitive              # launcher CLI z checkoutu
Makefile
```

## Instalacja i uruchomienie

CLI wymaga Pythona ≥ 3.11. Pełna aplikacja wymaga Docker Engine z Compose, Git, make oraz skonfigurowanego **istniejącego** `subactor/llm-account-hub`. Obecny launcher jest przeznaczony dla lokalnego Linuksa: korzysta z usługi użytkownika `llm-account-hub.service`, konta `softreck` i sieci `llm-account-hub-network`. Nie instaluje samodzielnie całego huba.

Z katalogu tego repozytorium:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
make start
```

`make start` przygotowuje prywatne kopie, sprawdza mounty, uruchamia aplikację i otwiera w przeglądarce:

- panel: <http://127.0.0.1:8793/>
- noVNC: <http://127.0.0.1:6083/vnc.html?autoconnect=true&resize=scale>

Domyślna lokalizacja huba to `/home/tom/github/subactor/llm-account-hub`; można ją wskazać przez `LLM_HUB_ROOT`. Dostęp noVNC bez hasła pozostaje ograniczony do interfejsu loopback. Pierwsze przygotowanie może potrwać ze względu na kopiowanie danych istniejących pulpitów.

```bash
./gitive menu           # stan, wykonane operacje i dostępne następne kroki
./gitive status
./gitive shell          # interaktywny shell komend Gitive
./gitive stop           # zatrzymaj pracę pętli aplikacji
make stop               # zatrzymaj kontener aplikacji; noVNC pozostaje uruchomiony
```

Po instalacji przez pip można używać `gitive` zamiast `./gitive`. CLI łączy się z działającą usługą; adres można zmienić przez `GITIVE_URL`. Sama instalacja paczki nie uruchamia serwera ani nie instaluje trzech silników benchmarku.

## LLM

W głównym `./.env` skonfiguruj wspólne ustawienia LiteLLM/OpenRouter:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL=openrouter/zai/glm-5.3
```

Wstaw własny klucz; przykład nie jest działającym credentialem. Wywołania live korzystają z płatnego endpointu. Praca kontrolera odbywa się w prywatnej kopii repozytorium, więc późniejsza edycja `.env` na PC nie jest automatycznie przenoszona do już istniejącej kopii. Nie dodawaj kluczy do Git ani raportów.

## Benchmark i development

```bash
./gitive benchmark
./gitive status
./gitive rank

./gitive project add moj-projekt /home/tom/github/organizacja/projekt \
  --goal 'Napraw błędy wykrywane przez testy' \
  --test 'python3 -m unittest discover -s tests' --allow src

./gitive project list
./gitive project run moj-projekt --cycles 3
./gitive project watch moj-projekt --interval 60
```

Dodanie projektu importuje jego kopię. Ranking korzysta z aktualnego, kompletnego benchmarku live: trzy rozwiązania wykonują po trzy iteracje na tych samych trzech projektach testowych. Raporty są zapisywane w `benchmark/runs/<timestamp-id>/` kopii roboczej. Szczegóły metodologii i zapisów wywołań LLM opisuje [benchmark/README.md](benchmark/README.md).

Aktualny development obsługuje poprawki 1–5 istniejących plików Python w zadanym zakresie oraz testy uruchamiane jako lista argumentów. Nie jest generatorem dowolnej aplikacji od zera. Dostępność etapu Codex zależy od wdrożonego API i uprawnień huba; nieudany preflight blokuje wykonanie. Integracje GitHub i warunki publikacji opisują README poszczególnych silników — lokalny sukces testów nie oznacza automatycznie wykonanego Issue → PR → merge.

| Silnik | Opis | Testy |
| --- | --- | --- |
| [GLM53](glm53/) | Fakty append-only w Git, krytyk i obsługa napraw PR | `make -C glm53 test` |
| [GPT6](gpt6/) | Kontroler GitHub, pamięć, weryfikacja SHA i publikacja | `python3 gpt6/scripts/test_all.py` |
| [Opus5](opus5/) | Ranking zadań i sprzężenie zwrotne z Git/CI | `python3 opus5/tools/offline_test_runner.py` |

## Kopie projektów i sesji: workspace

Operacje workspace są dostępne w CLI, interaktywnym shellu i formularzach panelu. Zatrzymaj pętlę przed rozpoczęciem kopiowania. Zamknij na PC przeglądarkę, której profil zamierzasz skopiować.

```bash
./gitive stop
./gitive workspace inspect
./gitive workspace inventory

# Projekt wraz z wybranym profilem Firefox z PC:
./gitive workspace snapshot moj-projekt \
  --project organizacja/projekt --browser firefox
./gitive workspace status

# Po zakończeniu wybierz snapshot z listy z datą i godziną:
./gitive workspace clone --target kopie/projekt
./gitive workspace status

# Po zakończeniu clone wybierz kopię z listy:
./gitive workspace resync --dry-run --include-sessions
./gitive workspace status
./gitive workspace resync --apply --include-sessions
./gitive workspace status
./gitive workspace resume --application terminal
```

Możesz pominąć ID: `./gitive workspace resync` wybierze jedyną kopię lub pokaże
listę wyboru w terminalu. W skrypcie przy kilku kopiach wymagane jest jawne ID; w terminalu wybierasz numer.
Domyślnie jest to podgląd; `--apply` zapisuje zmiany, a `--include-sessions`
obejmuje również wcześniej skopiowane profile. Bez istniejącej kopii potrzebny
jest najpierw snapshot i clone. CLI wyświetla wtedy instrukcję krok po kroku
z przykładowymi komendami, wyborem przeglądarki i sposobem odczytania ID.

`workspace status` pokazuje ostatnią operację i podpowiedź następnego kroku.
Sam status nie wykonuje kopii; zakończony snapshot nie oznacza wykonanego clone
ani aktywowania profilu w noVNC. Domyślnie CLI pokazuje krótkie podsumowania. Pełne dane są dostępne przez
`--json`, np. `./gitive workspace status --json` lub `./gitive workspace inspect --json`.

Operacje wykonują się w tle — przed kolejną zależną operacją poczekaj na zakończenie widoczne w `workspace status`. Dodanie `--include-sessions` do **snapshotu** obejmuje również obsługiwane dane sesji CLI/LLM/IDE. `--browser` wybiera `firefox`, `chrome`, `chromium`, `all` lub `none`.

Snapshoty są szyfrowane przez `age`. Profile PC po odtworzeniu pozostają kopiami offline; nie zastępują automatycznie aktywnej przeglądarki noVNC. Klucz `identity.age` w prywatnym magazynie workspace wymaga osobnej kopii zapasowej.

Osobne komendy obsługują profil istniejącego konta **noVNC `softreck`**, a nie profil PC:

```bash
./gitive workspace profile snapshot --browser firefox
./gitive workspace status
./gitive workspace profile restore
```

Snapshot/restore profilu huba może zatrzymać pulpit i jego procesy. Skrót `Chromium noVNC — data` na pulpicie pokazuje ostatni zapis plików sesji Chromium, odświeżany co minutę; nie jest potwierdzeniem importu Chrome z PC.

## Izolacja i aktualne ograniczenia

- PC jest źródłem tylko do odczytu. Praca agentów i resync zapisują prywatne kopie w `~/.local/share/gitive-isolated`; noVNC nie ma współdzielonego do zapisu oryginalnego katalogu projektów.
- Importowane są wskazane projekty, a nie całe `~/github`. Zmiany w kopii blokują resync zamiast być automatycznie nadpisywane. Nie ma automatycznej synchronizacji zwrotnej na PC.
- **Obecny import nie jest pełną kopią środowiska:** zachowuje m.in. `.git`, `.env` i zwykłe pliki nieśledzone, ale pomija `.venv`, `venv`, `node_modules`, `.subactor` i cache. Zewnętrzne symlinki oraz repozytoria z zewnętrznym `.git` wymagają osobnego eksportu.
- Pełna kopia wszystkich plików projektu, identyczna ścieżka jak na PC oraz osobny kontener z dokładnie zgodnym Pythonem, Node i bibliotekami systemowymi to wymagania **jeszcze niewdrożone**.
- Kopia profilu nie odtwarza procesów RAM. Restart kontenera nie oznacza automatycznego wznowienia zadania Codex.

## Testy i dokumentacja

```bash
make test-loop          # testy pakietu aplikacji
make test               # wszystkie zestawy repozytorium
```

Po przeniesieniu do `src/gitive` przeszło 29 testów aplikacji; sprawdzono budowę i instalację wheel, uruchomienie kontenera oraz izolację mountów. Nie jest to deklaracja pełnej zgodności środowiska z PC.

- [Dokumentacja aplikacji, komendy i historia weryfikacji](docs/information/benchmark-codex-loop.md)
- [Indeks dokumentacji](docs/README.md)
- [Benchmark](benchmark/README.md)

Menu stanu jest dostępne także na początku panelu WWW i po wejściu do `./gitive shell`.
W shellu wpisz numer pozycji lub `menu`, aby odświeżyć widok. Menu pokazuje ostatnią
operację oraz zapisane snapshoty i kopie; nie przedstawia samego snapshotu jako
odtworzonej przeglądarki. Podgląd menu nie uruchamia kopiowania ani płatnego benchmarku.

W interaktywnym shellu wpisz `sync` lub `pomoc`, aby zobaczyć instrukcję
PC → kopia → resync. Ta sama instrukcja: `./gitive sync-help`. Statusy i podpowiedzi
są kolorowane w terminalu; `NO_COLOR=1`, przekierowanie do pliku i `--json`
pozostawiają wyjście bez kolorów.

Snapshoty i kopie można wybierać z datowanej listy, bez ID: `workspace clone`,
`workspace resync`, `workspace resume` i `workspace profile restore`. Wybór jest
numerowany; czas podawany jest w Europe/Warsaw. Clone pyta także o nowy katalog,
jeśli pominięto `--target`. Starsze rekordy bez daty są oznaczone jawnie.
Ręczne ID pozostają obsługiwane w skryptach; pełne rekordy dostępne przez `--json`.

Walidacja nowych kontraktów (bez uruchamiania kontenerów lub publikacji):

```bash
python3 -m pip install ".[contracts]"
make test-contracts
```


### Planfile per projekt

Aktywne tickety są zarządzane przez **semcod/planfile**, lokalnie w `.planfile/`
prywatnej kopii projektu. Gitive używa wspólnego adaptera dla GLM53/GPT6/Opus5.
Jawna synchronizacja GitHub korzysta z natywnego GitHubBackend i lokalnego `gh`
(lub GH_TOKEN/GITHUB_TOKEN), bez zapisywania tokenu w konfiguracji ticketu.

```bash
./gitive tickets list doctor-agent
./gitive tickets create doctor-agent --title 'Sprawdzenie integracji' --engine glm53 --key unikalny-klucz
./gitive tickets sync doctor-agent --repo subactor/doctor-agent --direction push
./gitive tickets sync doctor-agent --repo subactor/doctor-agent --direction pull
```

`push` tworzy/aktualizuje zdalne Issue, `pull` odczytuje powiązane Issue. Przy
konflikcie operacja zatrzymuje się bez nadpisania. Samo uruchomienie pętli Gitive
zapisuje lokalny ticket; publikacja pozostaje jawna. Bezpośrednie uruchomienie
samodzielnych CLI silników nie przechodzi przez ten adapter Gitive.
Kontener zawiera zweryfikowany wheel Planfile. Dla CLI na innym hoście zainstaluj
`python3 -m pip install src/gitive/vendor/planfile-0.1.124-py3-none-any.whl`.

Przy imporcie klientów PC można jawnie pominąć aktywną sesję tej rozmowy:
`--include-sessions --exclude-session .codex`. Wykluczenie zostaje zapisane w manifeście.
