# Dockerowa pętla benchmark / Codex

```json
{
  "id": "benchmark-codex-loop",
  "kind": "information",
  "version": 16,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-running-live-benchmark",
  "evidence": ["src/gitive/engine.py", "src/gitive/hub.py", "src/gitive/compose.yaml", "src/gitive/tests/test_engine.py"]
}
```

Aplikacja działa pod **http://127.0.0.1:8793**. Wykorzystuje istniejący pulpit `llm-account-hub-softreck` pod **http://127.0.0.1:6083/vnc.html**. Nie tworzy drugiego pulpitu ani konta Codex. Obraz aplikacji zawiera Python, Node 22, Git, make i zależności benchmarku.

## Cykl

1. Uruchomienie `benchmark/run.py`: trzy rozwiązania × trzy projekty × trzy iteracje.
2. Walidacja kompletności raportu i receiptów zapisów LLM.
3. Codex otrzymuje ścieżki raportów i instrukcję analizy oraz ograniczonej poprawki modułów trzech rozwiązań. Zapisuje prywatny raport JSON z ustaleniami, zmianami i ograniczeniami; kontroler porównuje deklarowane pliki z rzeczywistą zmianą.
4. Zewnętrzny kontroler sprawdza zakres zmiany i uruchamia `make test`.
5. Ponowny benchmark, porównanie końcowych testów i zatrzymanie przy regresji.
6. Kolejny cykl wykorzystuje ostatni wynik jako bazę.

Plan wykonania Codexa przechodzi przez rzeczywiste API huba: plan → grant → intencja → apply. Używany jest jego allowlistowany Codex w koncie `softreck`, provider `chatgpt`, projekt `semcod/gitive`, timeout 300 s. Prompt idzie przez stdin. Konto Codexa i jego model pozostają konfiguracją huba; benchmark korzysta z `LLM_MODEL` i `OPENROUTER_API_KEY` w głównym `./.env`. Nie nadpisuje się modelu konta Codex modelem OpenRouter.

Tryb nieinteraktywny Codexa jest opisany w [oficjalnej dokumentacji](https://developers.openai.com/codex/noninteractive). noVNC daje podgląd pulpitu i możliwość ręcznej interwencji; nie jest transportem automatycznego klikania ani gwarancją widocznego okna procesu Codexa.

## Uruchomienie

```sh
python3 src/gitive/setup.py
docker compose -f src/gitive/compose.yaml up -d --build
```

`setup.py` pobiera tylko `CONTROL_API_TOKEN` z konfiguracji istniejącego huba i zapisuje prywatny plik 0600. Dane logowania Codexa pozostają w hubie. Domyślny katalog huba można zmienić przez `LLM_HUB_ROOT`.

Compose obsługuje `HUB_URL`, `NOVNC_URL`, `LOOP_PORT`, `LOOP_UID` i `LOOP_GID`. Domyślny Control to `http://10.240.0.1:8088`; localhost:8088 na tym hoście obsługuje inną usługę. Domyślny port panelu 8793 wybrano, ponieważ 8787 i 8788 były zajęte. Dla dostępu z innej maszyny użyj tunelu SSH i dostosuj adres noVNC. Usługa publikuje port tylko na loopback.

Panel domyślnie wybiera demonstrację: benchmark wykonuje swoje kontrolowane przypadki w trybie mock, Codex i testy po patchu są pomijane. Nie jest to dowód skuteczności LLM. Wyłączenie demonstracji wybiera rzeczywistą pętlę. Przed pierwszym benchmarkiem preflight wymaga, aby Hub materializował pięć stałych argumentów trybu `codex exec`.

Można wybrać 1–20 cykli lub 0 dla ciągłej pracy. Przycisk stop zatrzymuje po bieżącym etapie, nie przerywa niepewnej operacji Codexa. Timeout lub restart nie powoduje automatycznego ponowienia operacji huba; stan przechodzi do blocked/interrupted, aby najpierw uzgodnić rzeczywisty wynik. Nowy start tworzy nowy identyfikator przebiegu.

Limit USD dotyczy wyłącznie raportowanych kosztów benchmarku i jest kontrolą między etapami, nie twardym limitem billingowym. Jeden benchmark może przekroczyć pozostałą kwotę. Codex ma osobne rozliczenie konta huba. Twarde limity należy ustawić u dostawców.

## Dane i granice

- Stan, historia, logi poleceń, prompty i receipts huba: `.subactor/recovery/loop-app/`, prywatne pliki 0600. Token nie jest wysyłany do przeglądarki.
- Raporty benchmarku: `benchmark/runs/<timestamp>/`; pełne requesty/odpowiedzi LiteLLM pozostają w jego prywatnym magazynie.
- Hub zwraca receipts i skróty stdout/stderr; nie daje aplikacji pełnego tekstu odpowiedzi Codexa. Nie przedstawiamy tych receiptów jako pełnych transkryptów Codexa.
- Edycje dotyczą istniejących modułów `.py` w `glm53/intuition`, `gpt6/intuition_github`, `opus5/src/intuition`. Zmiany testów, benchmarku i historii Git blokują dalszy cykl; pliki pozostają do przeglądu, bez automatycznego kasowania pracy.
- Kontrola zakresu jest kontrolą po wykonaniu, nie izolacją systemową. Hub montuje szerszy workspace. Benchmark wykonuje kod w kontenerze aplikacji; to nie jest środowisko dla celowo wrogiego kodu. Gniazdo Dockera nie jest montowane do aplikacji. `/tmp` ma jawne `exec`, ponieważ testy Git uruchamiają hooki z tymczasowych repozytoriów.
- Nie ma automatycznego Issue → PR → merge → tag. Publikacja nadal wymaga niezależnego, chronionego Validatora.

## Potwierdzony status i blokada rzeczywistego trybu

Obraz zbudowano i uruchomiono; healthcheck przechodzi. W kontenerze przeszedł pełny `make test`: GLM53 28, GPT6 Python 25 + TypeScript 25 + crosscheck + GitHub 87, Opus5 20, benchmark 11. Pełny cykl demonstracyjny zakończył dwa benchmarki po 27 iteracji. Osiem testów silnika sprawdza kolejność, ponowne wykorzystanie bazy, błąd testów, regresję, restart i wiązanie uprawnień huba.

Rzeczywisty Hub poprawnie wykonał kontrolowane `codex --version` z grantem i intencją. Canary zadania tylko do odczytu zakończyło się kodem 1: obecna operacja task materializuje puste argv i uruchamia interaktywny Codex bez terminala. Nie wykonano jeszcze rzeczywistego pełnego cyklu napraw.

Przygotowano lokalną poprawkę w repozytorium `/home/tom/github/subactor/llm-account-hub`, na gałęzi `fix/ticket-030-codex-exec`: stałe `exec --json --sandbox workspace-write -`, bez dowolnego argv od klienta. Zaktualizowano skrót DSL i dodano testy. Przeszło 15 testów DSL. Stary test CLI wymaga migracji oczekiwania argv przez właściciela workstreamu application; gotowy minimalny diff jest w [hub-test-migration.patch](../../src/gitive/hub-test-migration.patch). Z nim testy DSL/CLI przeszły 25 przypadków, ale zmiana tego testu została wycofana z gałęzi DSL ze względu na kontrolę własności.

Gate huba wykazuje również wcześniejszy problem `ticket-008` bez README. Uruchomiony Control pochodzi z osobnego wdrożenia `.deployments/llm-account-hub-637084d`, którego nie zmieniano. Poprawka wymaga dokończenia walidacji i wdrożenia zgodnego z polityką huba. Panel blokuje rzeczywisty start na starej wersji przed poniesieniem kosztu benchmarku. To działająca aplikacja z przetestowanym demo i przygotowaną integracją, nie potwierdzone produkcyjne wdrożenie autonomicznego Codexa.

Potwierdzenie: [testy aplikacji i canary](../../benchmark/runs/20260910T131510Z-loop-app/verification.json). Zmiany pozostają lokalne, bez commita i publikacji.

## Aktualizacja v2 — uruchamianie i projekty developmentu

Stan lokalny z 2026-09-10, rozszerzenie v1. Wspólna baza źródeł: commit
`9bf5c8618de5b1b1cf7edf93a27394298999381e` plus lokalne zmiany opisane przez hashe
w manifeście każdego benchmarku. Nie wykonano publikacji ani merge na GitHubie.

```sh
make start              # kontenery + panel + noVNC w przeglądarce
./gitive benchmark      # rzeczywisty wspólny benchmark, zadanie w tle
./gitive status
./gitive rank
make shell              # interaktywne gitive>
./gitive project add moja-aplikacja /home/tom/github/moja-aplikacja \
  --goal "Napraw zachowanie opisane w testach" \
  --test "python3 -m unittest discover -s tests" --allow src
./gitive project run moja-aplikacja --cycles 3
./gitive project watch moja-aplikacja --interval 60
./gitive project list
./gitive stop            # zakończenie po bieżącym etapie
```

`make start` ustawia `VNC_PASSWORD_SOFTRECK=none`, przygotowuje izolowane kopie
i kontroluje mounty istniejących pulpitów huba oraz lokalne wiązanie portu.
Potwierdzono RFB 3.8 z typem bezpieczeństwa **1 (None)**. Port 6083 pozostaje na
loopback. Launcher otwiera dashboard w Chromium na istniejącym pulpicie; widok
`?desktop=1` nie osadza ponownie noVNC. Bieżące etapy i wyniki iteracji pochodzą
z rzeczywistego procesu benchmarku, a nie z animacji postępu.

Rejestr projektów jest prywatnym plikiem `projects.json` w katalogu danych.
Compose udostępnia źródłowe `/home/tom/github` aplikacji wyłącznie do odczytu
jako `/source/github`. `/workspace/github` zawiera niezależne kopie w prywatnym
magazynie Gitive. `GITIVE_GITHUB_ROOT` wskazuje źródło importu. Dodany projekt musi mieć
własne repo Git. Testy są poleceniem argv podanym przez użytkownika, bez shellowego
eval. Obecny kontrakt obsługuje naprawy **1–5 istniejących plików Python** w wybranym
katalogu. Nową funkcję należy opisać testami, które początkowo nie przechodzą.
Nie jest to generator dowolnej aplikacji od pustego katalogu.

Ranking bierze najnowszy kompletny benchmark **live v3** obejmujący identyczne trzy
projekty i trzy iteracje, po 37 testów końcowych. Odrzuca mock, piloty, niepełne
wyniki i hashe niezgodne z bieżącymi źródłami. Kolejność kryteriów: zaliczone testy,
zielone projekty, zielone etapy, liczba błędów, regresje, koszt. Remis rozstrzyga
nazwa rozwiązania. Zmiana źródeł unieważnia ranking i wymusza nowy przebieg.

Development używa natywnych planerów i walidatorów wybranego rozwiązania. Testy
uruchamiają się w osobnym klonie. Wewnętrzne commity pamięci planera nie trafiają
do projektu. Dopiero poprawka przechodząca testy i kontrolę zakresu otrzymuje jeden
commit, przenoszony przez fast-forward po ponownym sprawdzeniu niezmienionego,
czystego checkoutu projektu. Każde rzeczywiste wywołanie SDK LiteLLM ma prywatny
zapis request/response i receipt; sekrety są usuwane. Limit wynosi cztery wywołania
SDK na próbę. Nie są to surowe bajty HTTP.

Po błędzie: raport projektu → benchmark wszystkich trzech rozwiązań → Codex na
podstawie obu raportów → `make test` → ponowny benchmark → sprawdzenie regresji →
nowy ranking → ponowna próba projektu. `watch` ponawia testy okresowo, również gdy
projekt jest zielony; zatrzymuje się po blokadzie lub limicie kosztu benchmarku.
Restart kontenera nie odtwarza niepewnej operacji automatycznie.

**Ograniczenie wdrożeniowe pozostaje:** bieżący Control huba wymaga wdrożenia
poprawki ticket-030, aby wykonywać zadania przez `codex exec`. Kontroler sprawdza
plan przed tym etapem i zapisuje stan `blocked`. Nie omija chronionego wdrożenia
huba. Sam benchmark, ranking i naprawa projektu przez LiteLLM działają niezależnie.
Cykl Issue → PR → niezależna weryfikacja → merge/tag nie jest automatycznie
uruchamiany przez tę aplikację; lokalny commit nie jest dowodem publikacji.

Testy wykonywanego kodu mają oczyszczone środowisko, ale nie osobną granicę
bezpieczeństwa systemu operacyjnego. To środowisko dla zaufanych lokalnych
projektów. Kontener ma dostęp do zamontowanych repozytoriów.

### Potwierdzone wykonanie v2

- Benchmark live: [20260910T132550Z-6f91fc](../../benchmark/runs/20260910T132550Z-6f91fc/report.md), 27/27 iteracji, GLM53 **32/37**, GPT6 **30/37**, Opus5 **25/37**. Koszt 0,123311 USD. Audyt potwierdził receipty wszystkich **40 wywołań SDK**.
- Wybrany GLM53 naprawił zarejestrowany `billing-demo`: **3/3 testy**, dwie pary request/response, jeden commit zmieniający tylko `src/core.py`.
- Tryb `watch` wykonał kolejne kontrole zielonego projektu, bez zapytań LLM; `gitive stop` zakończył monitorowanie.
- Pełne `make test` w kontenerze zakończyło się kodem 0. Obejmuje wszystkie rozwiązania, 11 testów benchmarku i 14 testów aplikacji, w tym przejście błąd → benchmark → naprawa → testy → ponowny wybór (z atrapą Codexa).
- [Bezpieczny zapis weryfikacji](../../benchmark/runs/20260910T133300Z-gitive-app/verification.json). Logi wykonania i treści rozmów pozostają w prywatnym katalogu recovery.

Wynik benchmarku wskazuje na problemy z formatem/ucięciem odpowiedzi GLM53 i GPT6 oraz odrzucenia poprawek Opus5 przez natywne testy. Ranking wybiera najlepszy wynik względny; nie stanowi gwarancji poprawności dowolnego projektu.

Po weryfikacji pozostawiono aktywny monitoring `billing-demo` co 60 sekund. Zatrzymanie: `./gitive stop`. Zmiany aplikacji i dokumentacji są lokalne, bez commita i publikacji w repozytorium gitive.

## Aktualizacja v3 — wybór folderu w panelu

Sekcja **Projekty developmentu** udostępnia przeglądanie `~/github/` po jednym
katalogu, także wewnątrz organizacji. Otwórz wybrany folder, aż panel rozpozna
korzeń repozytorium Git. Podaj nazwę, cel, katalog źródeł i komendę testów, następnie
wybierz **Dodaj bieżący folder jako projekt**. Dodanie nie uruchamia LLM.
Zarejestrowany projekt można wybrać z listy i uruchomić development lub monitoring.

API `GET /api/folders?path=...` zwraca wyłącznie katalogi w zamontowanym workspace.
Ścieżki wychodzące poza ten katalog, również przez symlinki, są odrzucane.
Sprawdzono nawigację zagnieżdżoną, rozpoznanie korzenia Git i blokadę wyjścia poza
workspace; kod JavaScript przechodzi kontrolę składni. Zmiana lokalna, bez publikacji.

## Aktualizacja v4 — dopasowanie okna

Panel korzysta z pełnej szerokości okna. Formularze dopasowują się do dostępnego
miejsca, a osadzony noVNC ma wysokość zależną od wysokości okna i parametr
`resize=scale`. Przycisk **noVNC na pełny ekran** powiększa sesję do całego ekranu.
Sprawdzono rzeczywisty układ w Chromium dla szerokości 390, 768 i 1440 px: brak
poziomego przepełnienia dokumentu. Pionowe przewijanie długiego panelu pozostaje
normalną nawigacją; pulpit noVNC jest skalowany do swojego obszaru. Zmiana lokalna.

## Aktualizacja v5 — interaktywny Codex na pulpicie

Istniejący Hub obsługuje otwieranie terminala przez `/v1/applications/launch`
(`application_id=terminal`, `provider=chatgpt`, `project=semcod/gitive`) oraz
obsługę klawiatury przez `/v1/kvm/control`. Ta interaktywna ścieżka nie korzysta
z wykonania `task` wymagającego poprawki ticket-030.

Uruchomiono widoczny Codex CLI w terminalu konta softreck, w katalogu Gitive,
z `--no-alt-screen --sandbox workspace-write`. Początkowy prompt prosi o analizę
ostatniego benchmarku bez zmiany plików. Potwierdzono ekran powitalny wymagający
logowania. **Analiza nie rozpoczęła się:** użytkownik musi zalogować Codexa w tym
koncie. Nie kopiowano danych uwierzytelnienia z innej sesji. Terminal powiększono
na pulpicie. Przyciski pętli Gitive nie sterują tą osobną interaktywną sesją.

## Aktualizacja v6 — workspace w CLI, shellu i formularzach

Wdrożono `gitive workspace inspect/status/inventory/snapshot/clone/resync/resume/profile`
oraz odpowiadające im formularze w sekcji **Kopia środowiska PC → noVNC**.
Operacje wykonują się w tle; stan i wynik odczytuje `workspace status`.
Zatrzymaj monitoring przez `gitive stop` przed mutacją workspace. Kontroler
serializuje zadania workspace i pętlę benchmarku. Restart oznacza rozpoczętą
operację jako `interrupted`, bez automatycznego powtarzania.

```sh
./gitive workspace inspect
./gitive workspace inventory
./gitive workspace snapshot pc-main --project organizacja/projekt \
  --include-sessions --browser firefox
./gitive workspace status
./gitive workspace clone SNAPSHOT_ID --target kopie/projekt
./gitive workspace resync CLONE_ID --dry-run --include-sessions
./gitive workspace resync CLONE_ID --apply --include-sessions
./gitive workspace resume CLONE_ID --application terminal
./gitive workspace profile snapshot --browser firefox
./gitive workspace profile restore --snapshot PROFILE_ID
```

`SNAPSHOT_ID`, `CLONE_ID` i `PROFILE_ID` pochodzą z wyników operacji; panel pokazuje
je na listach wyboru. `resume` obsługuje terminal, VS Code i Cursor przez natywne
API huba. Otwiera aplikację w kopii projektu, nie uruchamia automatycznie rozmowy
LLM ani nie odtwarza procesów RAM.

### Wykorzystane zależności

- **Subactor llm-account-inventory 0.7.0**: zainstalowany wheel z istniejącego
  `subactor/llm-account-inventory/dist`. Jego SHA-256 i zaobserwowany HEAD repo
  zapisuje `src/gitive/vendor/manifest.json`; HEAD nie jest deklaracją pochodzenia
  buildu. Obraz sprawdza hash wheel przed instalacją. `workspace inventory` używa
  natywnego `llm-accounts scan`, bez eksportu wartości credentiali i bez głębokiego
  skanowania całego home. Raport jest prywatny.
- **Istniejący llm-account-hub**: natywne API snapshot/restore profili i launch
  aplikacji. Nie instalowano drugiej kopii serwera ani nie zmieniano jego wdrożenia.
- **age** z repozytorium pakietów obrazu Debian: szyfrowanie archiwów projektu i
  opcjonalnych profili PC. Nie jest to własna implementacja kryptografii.

### Zakres i odtwarzanie

Domowy katalog PC jest montowany tylko do odczytu jako `/host-home` (konfiguracja
`GITIVE_PC_HOME`). Wybrane repozytorium jest kopiowane z `.git` i plikami nieśledzonymi.
Katalog kontrolera, jego przodkowie i worktree z zewnętrznym `.git` są odrzucane.
Wykluczenia cache, `.subactor`, virtualenv i node_modules są zapisane w manifeście.
To kopia wybranego środowiska, a nie obraz całego systemu operacyjnego.

Opcjonalna lista profili obejmuje Codex, Claude, Continue, konfigurację Aider,
Code/Cursor, Subactor Shell i historię shella oraz wybraną przeglądarkę PC.
Formularz i `inspect` pokazują obecność źródeł. Przed kopiowaniem trzeba zamknąć
aplikacje zapisujące profile; zmiana wykryta w czasie kopiowania przerywa operację.
Nie ma gwarancji przenośności logowania pomiędzy komputerami i wersjami aplikacji.

Archiva `payload.tar.age` i metadane są w prywatnym `/data/workspaces`. Klucz
`identity.age` ma uprawnienia 0600, jest poza archiwami i wymaga osobnej bezpiecznej
kopii zapasowej — bez niego nie da się odszyfrować snapshotów po utracie dysku.
Po `clone` profile są odtworzone w `/data/workspaces/restored-home-CLONE_ID`, jako
**kopia offline**. Nie nadpisują aktywnego home PC ani profilu konta noVNC.
`resync --include-sessions` aktualizuje także te kopie offline; zmiany w nich
blokują synchronizację tak samo jak własna praca w kopii projektu.

Zwykły `resync` synchronizuje tylko projekt. Domyślnie pokazuje różnice.
`--apply` działa jedynie przy niezmienionej kopii docelowej; zachowuje poprzedni
katalog jako backup i sprawdza stabilność źródeł przed podmianą. Konflikty nie są
rozstrzygane automatycznie. Archiwum jest weryfikowane przez hash przed odszyfrowaniem,
a ekstrakcja stosuje filtr bezpiecznych ścieżek. Symlinki poza kopiowane drzewo są
odrzucane.

`workspace profile` dotyczy istniejącego konta **softreck w hubie**, nie profilu
PC. Hub wykonuje snapshot w swoim natywnym, prywatnym magazynie; nie deklarujemy
szyfrowania jego natywnego tar.gz. Snapshot/restore może zatrzymać pulpit i jego
procesy. Przywrócenie wymaga ID snapshotu zapisanego przez Gitive. Automatyczny
import profilu PC do aktywnego konta nie jest dostępny przez wdrożone API huba;
kopie PC pozostają offline. Wartości sekretów nie trafiają do wyników CLI ani UI.

Zmiany są lokalne, bez publikacji na GitHubie.

### Weryfikacja v6

Pełne `make test` w obrazie z nowymi zależnościami zakończyło się kodem 0, w tym
24 testy aplikacji. Osiem testów workspace obejmuje szyfrowanie, uprawnienia plików,
nieśledzone pliki, integralność archiwum, blokadę wyjścia poza drzewo, resync i
konflikty profili offline, adapter resume oraz brak testowego tokenu w inwentaryzacji.

Przez działające CLI wykonano snapshot → clone → dry-run → apply → konflikt bez
nadpisania → otwarcie terminala przez Hub. Interaktywny shell wykonał
`workspace inspect`. W rzeczywistym Chromium sprawdzono pięć formularzy i utworzono
snapshot projektu testowego przez formularz, bez błędów JavaScript.
[Zapis weryfikacji](../../benchmark/runs/20260910T140300Z-workspace/verification.json).
Nie kopiowano osobistych profili PC i nie uruchamiano snapshotu aktywnego kontenera
przeglądarki; adapter profili Hub sprawdzono z atrapą odpowiedzi, aby nie przerwać
użytkownikowi sesji. Monitoring demonstracyjny jest zatrzymany; operacje workspace
są dostępne bez konkurującej pętli.


## Izolacja danych PC — v7

Wcześniejsze mounty RW katalogu PC zostały zastąpione kopiami. Ta sekcja zastępuje
wcześniejszy opis współdzielenia workspace. Aktualny przepływ to **PC → kopia →
praca agenta**, bez automatycznej synchronizacji zwrotnej na PC.

- Prywatny magazyn: `/home/tom/.local/share/gitive-isolated` (0700).
- Oba istniejące pulpity, `softreck` i `prototypowanie`, mają wyłącznie prywatne
  bind mounty: kopie projektów, oddzielne profile użytkownika i kopie zasobów runtime.
- Aplikacja Gitive ma źródła `/source/github` i `/host-home` zamontowane RO.
  Zapisy projektu, benchmarku i stanu trafiają do prywatnych kopii.
- Dodanie projektu z formularza lub CLI wykonuje import niezależnych plików.
  Edycja kopii nie zmienia oryginału. Nie stosujemy hardlinków do plików PC.
- `clone` i `resync --apply` zapisują tylko w przestrzeni kopii. Zmodyfikowana
  kopia blokuje resync; oryginały PC nie są jego celem.
- Dawne rejestry projektów i klonów zachowano jako `*.before-isolation*`;
  wcześniejsze projekty należy ponownie dodać, aby zaimportować kopię.

Profile pulpitów skopiowano po zatrzymaniu ich kontenerów, następnie uruchomiono
oba konta ponownie. Oryginalne katalogi zachowano. Zmieniono operacyjne ustawienia
workspace huba, wskaźniki jego katalogów home oraz wygenerowane mounty Compose;
kod niezmiennego wdrożenia Control pozostał bez zmian. Backup konfiguracji jest
w prywatnym magazynie. Restart kontenera zachowuje dane profilu, ale nie zachowuje
procesu Codex w pamięci; wznowienie zadania wymaga obsługi sesji.

`make start` audytuje istniejące mounty, zatrzymuje kontenery wymagające migracji,
sprawdza scalony plan Compose przed uruchomieniem oraz rzeczywiste mounty po nim.
Plan noVNC z bind mountem poza prywatną przestrzenią jest odrzucany.
Zmiana konfiguracji Dockera poza tym mechanizmem wymaga ponownego audytu.

### Weryfikacja v7

Na działających kontenerach próby zapisu do źródła przez oba aliasy aplikacji
zwróciły `EROFS`. Zapis z każdego pulpitu noVNC zmienił tylko kopię pliku testowego;
hash oryginału PC pozostał identyczny, a inode kopii był inny. Audyt objął oba
pulpity i aplikację. Test nie modyfikował osobistych plików ani profili PC.

Pełne `make test` zakończyło się kodem 0, w tym 29 testów aplikacji.
Testy obejmują niezależność kopii, odrzucanie niebezpiecznych mountów, rozdzielenie
źródeł i celów oraz resync z konfliktem bez zapisu na PC.

[Zapis weryfikacji izolacji](../../benchmark/runs/20260910T142139Z-copy-only/verification.json).
Zmiany i dokumentacja są lokalne, bez commita ani publikacji na GitHubie.


## Skrót sesji przeglądarki — v8

Pulpity noVNC mają dodatkowy skrót `Chromium noVNC — YYYY-MM-DD HH:MM:SS`.
Data oznacza najnowszy zapis plików Session/Tabs prywatnego profilu Chromium,
w strefie Europe/Warsaw; nie oznacza importu Chrome z PC. Odświeżenie następuje
co 60 sekund. Skrót otwiera ten sam profil z opcją przywrócenia ostatniej sesji.
Updater startuje przy logowaniu pulpitu i przez `make start`; blokada zapobiega
uruchomieniu kilku updaterów jednocześnie. Odczytuje wyłącznie czasy plików.

Wdrożono na obu istniejących kontach. Sprawdzono wygenerowany plik wykonywalnego
skrótu oraz proces odświeżania; nie zmieniano profili PC.


## Układ pakietu — v9

Cały pakiet aplikacji znajduje się w `src/gitive`: CLI, serwer i panel, obsługa
projektów i workspace, integracja noVNC, konfiguracja Docker, zależność vendored
oraz testy. `pyproject.toml` definiuje pakiet instalowalny i entry point `gitive`.
Z katalogu repo nadal działają `./gitive`, `make start`, `make stop` i `make test`.
Instalacja CLI: `python3 -m pip install .` we własnym virtualenv.

Rozwiązania GLM53/GPT6/Opus5 i benchmark pozostają osobnymi komponentami repo.
Instalacja samej paczki CLI łączy się z działającą usługą Gitive; nie zawiera trzech
silników badawczych. Uruchomienie pełnego kontrolera przez Makefile wymaga repo.
Projekt Compose zachowuje nazwę `loop_app`, dzięki czemu przeniesienie źródeł
nie tworzy drugiej aplikacji ani nowych magazynów danych.

Weryfikacja v9: 29 testów aplikacji przeszło po zmianie importów. Zbudowano wheel,
zainstalowano go w osobnym virtualenv i uruchomiono `gitive workspace --help`.
Kontener przebudowano i uruchomiono; CLI `workspace inspect` odpowiada, a audyt
mountów nadal potwierdza izolację kopii. Zmiany lokalne, bez publikacji.


## Resync bez ID — v10

`./gitive workspace resync` automatycznie wybiera jedyną istniejącą kopię.
Przy kilku kopiach terminal pokazuje numerowaną listę, a wywołanie nieinteraktywne
wymaga ID. Bez kopii polecenie wyjaśnia konieczność snapshot → clone.
Domyślny tryb pozostaje dry-run. Zapis wymaga `--apply`, a aktualizacja wcześniej
skopiowanych profili — `--include-sessions`. Nie dodano importu aktywnego profilu
PC do przeglądarki noVNC. Cztery testy CLI potwierdziły wybór, brak kopii,
niejednoznaczność oraz zachowanie jawnego ID i flag. Zmiana lokalna.


## Menu stanu — v11

`gitive menu`, wejście do `gitive shell` oraz początek panelu WWW pokazują wspólny
odczyt `/api/overview`: stan pętli, powód blokady, ostatnią operację workspace,
liczbę zapisanych zasobów i ostatnie dostępne snapshoty/kopie. Menu rozróżnia
snapshot bez profili, odtworzoną kopię i aktywną operację. Nie deklaruje pełnej
historii zdarzeń; informacje pochodzą z aktualnego stanu i zachowanych zasobów.
W shellu numer wybiera polecenie, a w WWW link prowadzi do formularza/szczegółów.
Przy trwającej operacji menu oferuje odczyty; przy gotowej kopii resync jest
podglądem. Zmiana lokalna, bez publikacji.


## Zwięzły widok — v12

CLI domyślnie pokazuje krótkie podsumowania statusu i listę zasobów, bez pełnych
rekordów JSON. `--json` włącza pełny wynik dla skryptów. Menu pokazuje liczniki
i pojedyncze wiersze akcji; szczegóły archiwów są w `workspace inspect`.
W panelu JSON ostatniej operacji jest schowany w rozwijanych szczegółach.


## Pomoc synchronizacji w shellu — v13

`sync`, `pomoc` i ostatnia pozycja menu pokazują instrukcję snapshot → clone →
resync wraz z wyborem przeglądarki, oczekiwaniem na zakończenie i ograniczeniem
profili offline. Poza shellem dostępne jest `gitive sync-help`. Pomoc nie uruchamia
operacji. ANSI działa wyłącznie w terminalu, respektuje NO_COLOR i TERM=dumb;
JSON pozostaje niekolorowany. Sprawdzono instrukcję w shellu i tryby kolorowania.


## Wybór z datowanej listy — v14

CLI clone/resync/resume oraz profile restore obsługują wybór numeru zamiast ID.
Listy CLI i formularze pokazują datę i czas Europe/Warsaw oraz projekt/profil.
Nowe rekordy clone i profilu mają created w UTC; stare bez daty nie są uzupełniane
domyślnymi czasami. Ręczne ID pozostają dla automatyzacji. W menu odtworzenie
kopii uruchamia wybór snapshotu, a następnie pyta o nowy katalog docelowy.


## Kontrakt workspace i zarządzania — v15

Poniższy podział zapisuje doprecyzowane wymagania użytkownika. Jest modelem
**docelowym**, nie potwierdzeniem wdrożenia nowych kontenerów czy kopiowania runtime.
Zastępuje wcześniejsze utożsamianie workspace z kopią pojedynczego repozytorium.

### Gitive jako zarządca

Gitive administruje rejestrem workspace, projektami Git, procesami, kontenerami,
stanem synchronizacji i wynikami benchmarków. Ma własny workspace narzędziowy
z noVNC, terminalami, wybranymi przeglądarkami i integracją Codex. noVNC jest
pulpitem dostępu do środowisk; nie jest silnikiem naprawy ani samym repozytorium.

Workspace projektu zawiera prywatne dane, repozytorium, konfigurację, środowisko
uruchomieniowe i procesy. Projekt działa w osobnym kontenerze zarządzanym przez
Gitive i dostępnym z pulpitu noVNC. GLM53, GPT6 i Opus5 są wykonawcami zadań
wybieranymi według aktualnego benchmarku. Cykl projektu obejmuje GitHub:
Issue → branch → testy w środowisku projektu → PR → kontrolowany merge.
Stan wykonawcy i wynik testu nie zastępują potwierdzenia publikacji na GitHubie.

### Co oznaczają clone i resync

Obiektem obu operacji jest **workspace**, zarówno narzędziowy Gitive/noVNC,
jak i workspace projektu. Workspace przeglądarki nie powinien wymagać wskazania
przypadkowego repozytorium Git. Projekt i środowisko są osobnymi elementami
rejestru, nawet gdy początkowo jeden workspace obsługuje jeden projekt.

- Clone przygotowuje niezależne środowisko na podstawie wskazanego źródła PC:
  pełnej kopii wybranego folderu projektu oraz jawnie wybranych zewnętrznych
  runtime i profili. Nie kopiuje automatycznie całego ~/github ani całego PC.
- Pełna kopia folderu obejmuje `.env`, `.git`, `.venv`, node_modules i lokalne
  zmiany. Sekrety pozostają w prywatnym magazynie, poza publikowanym obrazem,
  raportem, promptami i automatycznym dodawaniem do Git.
- Ścieżka projektu wewnątrz jego kontenera odpowiada ścieżce na PC. Źródłem
  zapisywalnego mountu jest prywatna kopia, nigdy oryginał na PC.
- Zewnętrzne zależności wymagają inwentaryzacji: wersje interpreterów Python,
  Node, narzędzi, bibliotek systemowych i miejsca wskazywane przez symlinki.
  Zgodność jest sprawdzana w kontenerze, a brak zgodności blokuje uruchomienie
  projektu. Sama obecność skopiowanej `.venv` nie potwierdza zgodności.
- Resync aktualizuje wskazany workspace z PC na żądanie, z podglądem zmian,
  kontrolą konfliktów, zachowaniem poprzedniej wersji i ponowną weryfikacją
  środowiska. Profile aplikacji kopiowane są po ich zatrzymaniu. Operacja nie
  nadpisuje PC ani nie przedstawia kopii danych jako kopii procesów RAM.
- Po pierwszym imporcie kod jest rozwijany przez GitHub. Aktualizacja repo z
  GitHub oraz ponowny import lokalnego workspace z PC to odrębne operacje.

Menu powinno rozdzielać: stan zarządcy, workspace Gitive/noVNC, workspace
projektów, procesy oraz wykonawców. Każdy workspace ma nazwę, typ, źródło,
czas ostatniego udanego importu, stan zgodności środowiska i dostępne działania.
Wyboru dokonuje się z listy z datą i godziną; wewnętrzne ID nie są wymagane w UI.

### Różnica względem wdrożenia

Obecny moduł workspace nadal wymaga repozytorium przy snapshotach, pomija część
katalogów i odtwarza profile offline. Nie ma jeszcze pełnego rejestru środowisk,
odwzorowania runtime PC ani osobnych kontenerów projektów. Zmiany prezentacji
CLI z wersji 10–14 nie wdrożyły tych funkcji. Wymagane są zmiany modelu danych,
importu i resync, provisioningu kontenerów, wykonania testów oraz menu — nie tylko
zmiana nazw komend. Ten zapis i README są lokalne, bez publikacji.


## Architektura i kontrakty — v16

Szczegółowy model workspace, projektu i ticketu jest utrzymywany w
[architekturze](workspace-project-architecture.md), a etapy wdrożenia w
[planie realizacji](../refactoring/workspace-delivery.md). Dodano schematy i szablony
w `src/gitive/contracts` oraz `src/gitive/templates`. Nie przełączono na nie
produkcyjnego importu ani egzekutora; opis bieżących komend pozostaje aktualny.
