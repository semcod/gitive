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
