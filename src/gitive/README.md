# Pakiet Gitive

Kod aplikacji obejmuje CLI, panel WWW, kontroler benchmarku, obsługę projektów i workspace oraz integrację z istniejącym noVNC Subactor.

Z katalogu głównego repozytorium:

```bash
python3 -m pip install .
make start
./gitive workspace inspect
make test-loop
```

Instalacja udostępnia komendę `gitive`, która łączy się z działającą usługą. Pełny kontroler wymaga repozytorium z benchmarkiem i trzema silnikami; samo zainstalowanie CLI ich nie dostarcza.

- [Główny README: instalacja, CLI i ograniczenia](../../README.md)
- [Dokumentacja workspace, noVNC i izolacji](../../docs/information/benchmark-codex-loop.md)

Obecne kopiowanie profili jest odtwarzaniem danych offline. Nie klonuje dokładnych wersji środowiska PC ani całego działającego pulpitu.

Kontrakty: `contracts/`; przykłady workspace i struktur projektu/ticketu: `templates/`.
Opis docelowego modelu: [architektura](../../docs/information/workspace-project-architecture.md).
Szablony nie uruchamiają nowych środowisk i nie alokują aktywnych ticketów.

## Nawigacja DigitalTwin

`gitive menu 4` i `gitive project open` otwierają panel projektu.
`gitive project new` prowadzi przez wybór repo PC, celu, testów i zakresu zmian.
Tickety: `tickets list/show/create/run/sync PROJEKT`; wykonania obserwuj przez
`project status PROJEKT`. Schemat DigitalTwin jest kontraktem przyszłego katalogu,
a P0 przechowuje relacje w digitaltwins.json i kompatybilnym projects.json.
Polecenia hosta `twin plan/prepare/status/test/exec/extend/recover` obsługują
pełne kopie wybranych projektów oraz prefiksów Python/Node.

[Architektura](../../docs/information/workspace-project-architecture.md) ·
[Plan](../../docs/refactoring/workspace-delivery.md).


## Shell z kontekstem

`./gitive shell` pokazuje `username/project/ticket/operation>` i zachowuje wybór
projektu oraz ticketu. `projects` → numer → `tickets` → numer; potem `status`,
`run`, `new`, `sync pull|push`, `operations`, `watch`, `back`. Aktualny etap
odświeża się co sekundę dzięki prompt-toolkit; bez tej zależności po poleceniu.
[Pełna instrukcja](../../docs/information/context-shell.md).


## Terminal projektu w noVNC

Na PC uruchom `./gitive twin terminal doctor-agent`, albo wybierz „Terminal
projektu w noVNC” w menu projektu. Na pulpicie pojawi się skrót Gitive projektu.
Terminal łączy się z jego prywatnym kontenerem jako właściciel repo z PC; zachowuje
UID/GID, HOME i ścieżkę źródłową. Migracja starszego runtime zachowuje poprzedni
kontener i kopie. Komenda wymaga hostowego dostępu Docker; nie przekazuje go
pulpitowi. Przy pierwszym otwarciu instaluje klienta SSH w kontenerze noVNC.
