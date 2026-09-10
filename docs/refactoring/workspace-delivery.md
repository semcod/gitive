# Realizacja workspace i projektów z ticketami

```json
{
  "id": "workspace-delivery",
  "kind": "refactoring",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "planned-with-contracts",
  "source_revision": "780db4aa186bcc16ebe425391e0a4a0dac056fb4",
  "evidence": ["src/gitive/contracts", "src/gitive/templates", "docs/information/workspace-project-architecture.md"]
}
```

## Cel

Rozdzielić zarządcę Gitive, środowiska workspace i projekty Git; realizować zadania
jako tickety w zweryfikowanym środowisku, z kontrolowaną publikacją na GitHub.
Kontrakt: [architektura](../information/workspace-project-architecture.md).

## Dostarczone w tym etapie

- Schematy workspace, projektu i ticketu oraz szablony w pakiecie `src/gitive`.
- Struktura projektu: kod w src, testy w tests, dokumentacja w docs, tickety w project.
- Opis prywatnego magazynu, importu środowiska i pełnego cyklu dostarczania.
- Walidacja przykładów, przypadków błędnych i dołączenia kontraktów do wheel.

To przygotowanie kontraktów, nie uruchomiony provisioning. Istniejące dane i
rejestracja workspace zachowują dotychczasowy format do etapu migracji.

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
