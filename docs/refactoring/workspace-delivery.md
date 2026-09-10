# Plan realizacji Gitive DigitalTwin

```json
{
  "id": "workspace-delivery",
  "kind": "refactoring",
  "version": 5,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "p0-implemented-publication-in-progress",
  "source_revision": "10152a58738b8a5cdabb29dd412dc163042d7ebe",
  "evidence": ["src/gitive/contracts", "src/gitive/templates", "docs/information/workspace-project-architecture.md"]
}
```

## Cel

Rozdzielić zarządcę Gitive, środowiska workspace i projekty Git; realizować zadania
jako tickety w zweryfikowanym środowisku, z kontrolowaną publikacją na GitHub.
Kontrakt: [architektura](../information/workspace-project-architecture.md).

## Dostarczone w tym etapie

- Schematy workspace, projektu i ticketu oraz szablony w pakiecie `src/gitive`.
- Struktura projektu: kod w src, testy w tests, dokumentacja w docs, tickety w `.planfile` zarządzanym przez semcod/planfile.
- Opis prywatnego magazynu, importu środowiska i pełnego cyklu dostarczania.
- Walidacja przykładów, przypadków błędnych i dołączenia kontraktów do wheel.

Pierwsza wersja dostarczyła kontrakty. Aktualizacja P0 poniżej dodaje runtime
i migrację konkretnego projektu, zachowując stare kopie oraz rejestry.

## Zweryfikowana aktualizacja 2026-09-10

Dostarczono `planfile_bridge.py`, integrację jobs.py dla trzech wykonawców oraz
jawne push/pull przez CLI. Trzy rzeczywiste Issue potwierdziły idempotencję i
synchronizację stanu. Dostarczono prywatną aktywację profili noVNC z backupem.
Automatyczny provisioning dokładnego środowiska projektu oraz pełna kontrolowana
ścieżka PR → merge pozostają niezweryfikowane w tym etapie.
[Raport](../analysis/planfile-doctor-agent-2026-09-10.md).

## Kolejność implementacji

| Etap | Zakres kodu | Warunek odbioru |
| --- | --- | --- |
| 1. Rejestr | wydzielenie `workspaces/catalog.py` z workspace.py i `delivery/projects.py` z projects.py | workspace browser bez repo; trwałe relacje, poprawne daty i wznowienie po restarcie |
| 2. Import | `workspaces/importer.py`, `inventory.py`, `sync.py` | pełne wybrane foldery, stabilna kopia, symlinki i zewnętrzne Git obsłużone jawnie, PC niezmieniony |
| 3. Runtime | `workspaces/runtime.py`, `environment.py`, kontrolowany adapter hosta | kontener projektu, ta sama ścieżka, zgodne wersje i biblioteki; mismatch blokuje start |
| 4. Procesy/UI | `workspaces/processes.py`, CLI i WWW | start/stop/readback kontenera, terminal z noVNC, oddzielny stan importu, środowiska i procesu |
| 5. Tickety | `delivery/tickets.py`, adapter governance repo | prawdziwa alokacja i rezerwacja zakresu; kryteria i dozwolone ścieżki przed zmianami |
| 6. Wykonawcy | adaptacja jobs.py/develop.py i adapterów trzech silników | testy w workspace projektu, zachowanie lokalnych plików i zależności, raport konkretnego SHA |
| 7. Publikacja | `delivery/github.py`, `verification.py` | idempotentne Issue/PR, niezależna weryfikacja, kontrolowany merge i odczyt stanu |
| 8. Wydanie/naprawa | `delivery/releases.py`, pętla engine.py | opcjonalny tag/release, kontrola wdrożenia, osobne tickety napraw wykonawców i benchmark bez regresji |

Nazwy nowych modułów określają docelową odpowiedzialność; nie są dziś zaimplementowanymi
adapterami. Przed implementacją wydzielić zadania przez właściwy alokator; tabela
nie nadaje rzeczywistych numerów ticketów ani uprawnień publikacji.

## Migracja bez utraty danych

1. Zatrzymać zapisujące operacje i zinwentaryzować istniejące kontenery/mounty.
2. Zapisać backup dotychczasowego app-data, rejestrów, manifestów i kluczy age.
3. Utworzyć nowy rejestr obok starego; nie modyfikować oryginalnych źródeł PC.
4. Zaimportować stare snapshoty jako archiwa danych, nie jako zweryfikowane runtime.
5. Przypisać daty tylko tam, gdzie są rzeczywiście zapisane; brak danych oznaczyć.
6. Przełączyć kontroler po sprawdzeniu referencji i dostępności kopii; zachować rollback.

Migracja nie usuwa historycznych katalogów, lokalnych zmian ani starych kluczy.
Resync musi chronić zmiany obu stron; nie stosować automatycznego reset/clean w repo PC.

## Scenariusze odbioru

- Browser workspace Firefox bez repo: import profilu offline, osobna aktywacja,
  oryginał niezmieniony, jednoznaczny wynik w noVNC i menu.
- Projekt Python: pełne `.env`/`.venv`, zależności zewnętrzne zinwentaryzowane,
  właściwa wersja interpretera, testy pod identyczną ścieżką jak na PC.
- Projekt Node: właściwa wersja Node, lockfile i moduły natywne zweryfikowane;
  niezgodność ABI blokuje ready zamiast deklarować udaną kopię środowiska.
- Resync z własną zmianą w kopii: konflikt i brak nadpisania, backup i udane
  odtworzenie poprzedniego środowiska po nieudanym provisioningu.
- Restart podczas importu lub zadania: jednoznaczne interrupted i brak fałszywego complete.
- Ponowienie publikacji: brak zdublowanych Issue/PR, zmieniony HEAD unieważnia testy,
  nieudana weryfikacja blokuje merge, tag wskazuje potwierdzony scalony commit.
- Błąd wykonawcy: osobny ticket Gitive, testy trzech silników, wspólny benchmark,
  brak równoczesnego nadpisania projektu rozwijanego przez użytkownika.

Wyniki operacyjne i logi przechowywać prywatnie; w dokumentacji publikować tylko
bezpieczne, ograniczone referencje i skróty. Każdy etap raportować osobno jako
zadeklarowany, zaimplementowany, uruchomiony i zweryfikowany.

## Plan po ocenie DigitalTwin — wersja 3

| Priorytet | Dostarczany efekt | Kryterium odbioru |
| --- | --- | --- |
| P0, wykonane lokalnie | Menu NUMER, kreator importu, panel projektu, list/show/create/run ticketów | wybór bez ID; test wykonuje wybrany ticket przypisanym silnikiem; rezultat zapisany w Planfile |
| P0, zaimplementowane | Jeden rejestr DigitalTwin → workspace → projekt → konto | migracja doctor-agent z dwóch prywatnych kopii bez utraty `.planfile`; jawne źródło prawdy i backup migracji |
| P0, zaimplementowane | Pełny import środowiska wybranego projektu | kopia `.env`, `.git`, zależności i wersji runtime; identyczna ścieżka wewnątrz kontenera; testy w tym kontenerze, nie interpreterem PC |
| P0, zaimplementowane | Pomiar pojemności przed importem | dodatkowa alokacja + jedna kopia rezerwy; przypadek 30/60 GB przechodzi bez ostrzeżenia; żadne kasowanie cudzych backupów |
| P1 | Aplikacje projektu: terminal, VS Code Web, przeglądarka | jedna prywatna kopia projektu widoczna w IDE i testerze; otwieranie z panelu noVNC; zgodność wersji i izolacja mountów |
| P1 | Tożsamości per workspace | wybór konta gh, odczyt loginu i repo, krótkotrwałe przekazanie poświadczenia; brak tokenów w image/JSON/logach; wygasłe konto blokuje tylko operację GitHub |
| P1 | Planfile DAG i trwała kolejka | parent/children oraz blocked_by; sprawdzenie cykli i brakujących referencji; próba ma własne ID, lease, heartbeat, timeout, retry, log i receipt |
| P1 | Obserwacja i restart | GUI/worker/container stan odczytany z runtime; po restarcie reconcile bez ponowienia ukończonego efektu; anulowanie całego drzewa procesów danego wykonania |
| P1 | Testy widoczne w GUI | deterministyczny ekran, locate → act → verify; trace/screenshot + wynik powiązany z ticketem i SHA; reprodukcja bez profilu PC RW |
| P2 | Platformy dodatkowe | Android: wybrany emulator/urządzenie i ADB; dla innego OS osobny worker/VM/urządzenie; jawna macierz możliwości zamiast obietnicy każdej aplikacji w jednym Dockerze |
| P2 | Issue → branch → testy → PR → merge → wydanie | idempotentne synchronizacje i konflikty, weryfikacja exact head/base przez niezależny lokalny Validator, brak automatycznej zgody na merge z wyniku LLM |
| P2 | Naprawa trzech silników w pętli | błąd projektu tworzy osobny ticket silnika, trzy wspólne fixtures × trzy iteracje, porównanie regresji, wznowienie pierwotnego ticketu dopiero po zaliczonych testach |

Kolejność: najpierw spójność rejestru i runtime, potem aplikacje/obserwacja/DAG,
a następnie pełne publikowanie. Wybrany silnik pozostaje przypisany do próby;
zmiana rankingu wpływa na następne zadania. Zestaw testów benchmarku nie zastępuje
testów docelowej aplikacji ani odbioru nowej funkcji.

## Istniejące komponenty znalezione przez subactor/search

Wyszukano `code-server`, `urirun`, `KVM` oraz katalog projektów browser/urirun.
Wyniki indeksu sprawdzono w aktualnych README, Dockerfile i kodzie adapterów.
To wybór kandydatów do Gitive; nie potwierdzenie ich wdrożenia w DigitalTwin.

| Komponent | Zbadany punkt integracji | Decyzja dla Gitive |
| --- | --- | --- |
| semcod/proxym | `services/vscode/{Dockerfile,entrypoint.sh}`, usługa vscode w docker-compose.yml | ponownie wykorzystać konfigurację code-server; podmienić RW mount źródła na prywatną kopię, zachować ścieżkę projektu, przypiąć obraz zamiast latest; potwierdzić rozszerzenia |
| subactor/llm-account-hub | istniejący noVNC i kontrolowany adapter uruchamiania | zachować jako control workspace; katalog aplikacji i izolacja per projekt |
| urirun-connectors/urirun-connector-kvm | `kvm://host/*`, `app://host/desktop/*` | screenshot, klawiatura, mysz, lista/uruchamianie okien w sesji X11 noVNC; samo przechwycenie obrazu nie dowodzi poprawnego kliknięcia |
| urirun-connectors/urirun-connector-browser-control | `browser://cdp/*`, `browser://kvm/*` | CDP do testów DOM Chrome, KVM do całego GUI i pozostałych przeglądarek; rozdzielić wykonanie rzeczywiste od mock |
| urirun-connectors/urirun-connector-vdisplay | trasy vdisplay, backend wronai/vdisplay | inwentaryzacja i diagnostyka okien/ekranów; ocenić sesję o stałej rozdzielczości per tester |
| urirun-connectors/urirun-connector-planfile | `task://host/tickets/*`, adapter urirun.host.planfile_adapter | most do wykonywalnych procesów URI; przed przyjęciem sprawdzić zgodność z przypiętym Store semcod/planfile 0.1.124 i brak drugiego magazynu |
| subactor/browser-agent | lokalny bridge DOM z jawnym potwierdzaniem działań | opcjonalny tryb operatora; nie oznaczać go jako autonomicznego zamiennika CDP |

KVM oznacza tutaj keyboard/video/mouse. Nie utożsamiamy tego konektora z
hiperwizorem Linux KVM używanym przez część emulatorów i maszyn wirtualnych.
Dokumentacja konektora ostrzega przed mapowaniem współrzędnych Wayland/HiDPI;
dla noVNC używamy wyświetlania i sterowania w tej samej wirtualnej sesji.

Nie uruchamiano obcego compose proxym: obecna definicja montuje wybrany katalog
RW i jest związana z siecią/proxy tamtego produktu. Gitive potrzebuje adaptera,
nie skopiowania całej konfiguracji bez zmian.

## Rozwinięcia warte wykonania

- Katalog aplikacji z capability probe: „zainstalowana”, „uruchomiona”,
  „gotowa do sterowania” i „zweryfikowana testem” jako oddzielne stany.
- Przyrostowy import po hashach oraz niezależne COW; pliki aktywnych aplikacji
  kopiowane w stabilnym punkcie, atomowa podmiana i odtwarzalny backup.
- Oddzielny profil browser do testów od profilu operatora; testy nie zmieniają
  zalogowanej sesji użytkownika, chyba że zadanie jawnie wskazuje tę sesję.
- Testy feature acceptance: nowe funkcje wymagają kryteriów i nowych prób;
  samo „dotychczasowe testy zielone” nie może zamykać dowolnego ticketu.
- Widok osi czasu: cel → zależności → wykonanie → test → publikacja; dopiero
  później edytor graficzny DAG. Źródło prawdy pozostaje w Planfile.

## Status dostarczenia tej aktualizacji

Kontrakty, CLI oraz P0 katalogu i provisioningu są zaimplementowane.
Nowe integracje VS Code/KVM/CDP pozostają planem. Nie uruchamiano nowych
płatnych benchmarków LLM ani nie publikowano zmian na GitHub w tym etapie.

Historia: v1 kontrakty; v2 Planfile/noVNC; v3 DigitalTwin, nawigacja, procesy,
reguła pojemności i wybór komponentów przez subactor/search.

Dowody tej aktualizacji: [subactor/search, rewizje źródeł i testy CLI](../../benchmark/runs/20260910T154643Z-digitaltwin-design/verification.json).

## Realizacja zatwierdzonego zakresu: gotowe zmiany + P0

Użytkownik wybrał publikację gotowych zmian i następny etap P0. Zaimplementowano
katalog i migrację z zachowaniem `.planfile`, pełne kopiowanie projektu oraz
prefiksów Python/NVM Node, kontrolę miejsca, kontener z identycznymi ścieżkami,
`twin status/exec/test` i odzyskiwanie niedokończonej transakcji `twin recover`.
Brak profilu `semcod/gitive` potwierdzono również w wdrożonym chronionym rejestrze
lokalnego Validatora. Push/PR nie będą raportowane jako niezależnie zatwierdzony merge.

Dalszy P1: przekazać wykonawcom GLM53/GPT6/Opus5 testy ich roboczych checkoutów
w przygotowanym runtime przez kontrolowany adapter hosta. Do tego czasu dla
projektów po migracji blokowane jest zastępcze wykonanie w kontenerze aplikacji.
Pozostają też GUI/VS Code/KVM, scheduler DAG, broker kont i automatyczna publikacja.

Status „ready” workspace oznacza poprawne uruchomienie skopiowanych interpreterów
oraz audyt mountów. Wynik testów projektu jest osobnym polem verification;
nie należy utożsamiać tych dwóch dowodów ani rozciągać ich na wszystkie pakiety PC.


## Ergonomia shellu — propozycja po obserwacji użytkownika

Status tej sekcji: **plan, nie zaimplementowano nowego selektora TUI**.
Terminal projektu z kontem/ścieżką PC jest już dostarczony osobno
([odbiór](../analysis/project-terminal-2026-09-10.md)).

Na pokazanej sesji ticket `done` nadal oferuje „Uruchom”, projekt bez adaptera
własnego runtime ujawnia blokadę dopiero po wybraniu akcji, a komunikat błędu
jest trudny do powiązania z poleceniem przy następnym promptcie.

| Priorytet | Zmiana | Kryterium odbioru |
| --- | --- | --- |
| 1 | Menu zgodne ze stanem | Ticket done nie oferuje uruchomienia; projekt bez adaptera runtime pokazuje przyczynę przed wyborem; dostępne testy/terminal pozostają aktywne |
| 2 | Spójny wynik polecenia | Stały obszar wyniku: polecenie, projekt/ticket, w toku/sukces/błąd; brak pomieszania wyników z następnym promptem; nie przyjmować kolejnego wyboru menu podczas zmiany kontekstu |
| 3 | Selektor strzałki + wyszukiwanie | ↑↓, Enter, Esc, filtrowanie po wpisaniu tekstu; skróty 1–9 opcjonalne; obsługa pustej listy i przewidywalnego powrotu |
| 4 | Powrót do pracy | Zapamiętany ostatni projekt/ticket i pozycja listy; „Kontynuuj” wybiera kontekst, nigdy automatycznie nie uruchamia efektu |
| 5 | Paleta Ctrl+P | Projekty, tickety i polecenia w jednym wyszukiwaniu; `terminal`, `testy`, `logi`, `synchronizuj` korzystają z wybranego projektu |
| 6 | Działania GitHub z podglądem | Lokalny/GitHub: równe, lokalne zmiany, zdalne zmiany, konflikt lub nieznany; kierunek sugerowany po odczycie, nigdy zgadywany z samego statusu done |

Ekran startowy powinien pokazywać osobno: dostępność serwera, pracę pętli,
aktualny/ostatni projekt, aktywny ticket i operację (lub brak), wynik ostatnich
testów z czasem oraz jedną najważniejszą blokadę i następny dostępny krok.
Po wyborze projektu dochodzą: status kontenera, połączenia GitHub, liczba ticketów
otwartych/zablokowanych oraz wiek ostatniej synchronizacji. Nieznane dane pozostają
jawnie nieznane; odświeżenie nie wykonuje synchronizacji ani naprawy.

Archiwa, sumy kontrolne, pełne ścieżki magazynu, wersje wszystkich zależności i
historia logów należą do rozwijanych szczegółów „Środowisko”. Otwarte tickety są
filtrem domyślnym; przełącznik „Zakończone / wszystkie” pokazuje próby #407–409.
Przy braku otwartych ticketów lista proponuje „Dodaj ticket”, a nie pusty wybór.
Po wybraniu zakończonego ticketu główne akcje to wynik, powiązane Issue i nowe
zadanie powiązane z poprzednim, zamiast uruchomienia zamkniętego zadania.

Menu główne docelowo: Kontynuuj → Projekty → Nowy projekt → Środowiska →
Benchmark/ranking. Menu projektu: Tickety → Terminal → Testy → Kod/Git →
Synchronizacja → Środowisko. Planowana paleta skraca obie ścieżki bez wymagania ID.
