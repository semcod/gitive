# Natywna dostawa GPT6 dla istniejących Issues w Gitive

```json
{
  "id": "native-gpt6-delivery-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "completed-and-verified",
  "ticket": "https://github.com/semcod/gitive/issues/15",
  "evidence": [
    "gpt6/intuition_github/selected.py",
    "src/gitive/delivery.py",
    "src/gitive/cli.py",
    "gpt6/tests_github/test_selected.py",
    "src/gitive/tests/test_delivery_cli.py"
  ]
}
```

## Podsumowanie i cel

Zadanie [Issue #15](https://github.com/semcod/gitive/issues/15) zrealizowało podłączenie kontrolera **GPT6** do obsługi istniejących, jawnie zaimportowanych zgłoszeń GitHub w Gitive.

Wcześniejsze próby wykazały, że żaden silnik w repozytorium nie potrafił w pełni autonomicznie zamknąć cyklu:
`istniejące GitHub Issue → ticket Planfile → naprawa → odizolowane testy w kontenerze → draft PR → merge`.

Rozwiązanie integruje maszynę stanów GPT6 z powiązaniem do Planfile (`gitive delivery`), izolując testy kandydata w kontenerze Docker bez dostępu do sieci i tokenów, zachowując niezależność publikacji (Draft PR bez samowolnego auto-merge).

---

## Architektura i komponenty

### 1. `SelectedController` (`gpt6/intuition_github/selected.py`)
Rozszerza kontroler GPT6 (`Controller`) o obsługę jawnie wybranego istniejącego Issue:
- **`import_issue(number, paths, acceptance)`**:
  - Waliduje otwarty status zgłoszenia i tożsamość URL (odrzuca Pull Requesty i zamknięte Issue).
  - Sprawdza listę dozwolonych plików źródłowych (`allowed_paths`) i kryteria odbioru (1–8 pozycji).
  - Weryfikuje brak konkurujących otwartych lub scalonych PR powiązanych z tym Issue (`Closes/Fixes #N`).
  - Gwarantuje **idempotentność**: ponowny import z identycznym zakresem zwraca istniejące zadanie; zmiana zakresu jest blokowana jako naruszenie tożsamości.
  - Rejestruje dowód w pamięci Git (`transport: gitive-local-review`).
- **`cycle_issue(tid, verifier)`**:
  - Sprawdza aktualny stan zdalny:
    - Zamknięcie Issue zdalnie → status `abandoned`.
    - Zmiana treści Issue zdalnie → status `needs_human`.
    - Scalenie PR zdalnie → status `completed`.
    - Zamknięcie PR zdalnie → status `abandoned`.
    - Zmiana HEAD PR poza dostawą → status `needs_human`.
  - Uruchamia generowanie łatki LLM i publikuje gałąź `intuition/issue-...`.
  - Tworzy Draft PR z informacją o dowodowym charakterze testów lokalnych.
  - Wywołuje `verifier(pr_number, head_sha, base_sha)`:
    - `passed` → status `awaiting_review`, wynik `local_pass`.
    - `failed` → status `ready`, wynik `local_fail`, zapisuje wyjście testów jako dowód dla kolejnej próby LLM.
    - Osiągnięcie limitu prób (`max_attempts_per_issue`) → status `needs_human`.

### 2. Mostek CLI i weryfikator kontenerowy (`src/gitive/delivery.py`)
- **`ReviewHub`**:
  - Nadpisuje `create_pull`: tworzy Draft PR (`--draft`) i dołącza klauzulę o wymogu niezależnego przeglądu.
- **`DockerVerifier`**:
  - Przygotowuje czysty klon repozytorium w katalogu tymczasowym.
  - Wykonuje `git merge-tree` między bazą a kandydatem — wykrywa konflikty przed uruchomieniem testów.
  - Archiwizuje drzewo źródeł i montuje je jako **read-only** (`/input`) w odizolowanym kontenerze Docker.
  - Uruchamia testy z parametrami bezpieczeństwa:
    `--network=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, pamięć 1GB, 1 CPU, bez uprawnień roota (`user=65534:65534`).
- **`run_cli(args)`**:
  - Obsługuje polecenia `gitive delivery {import,run,status}`.
  - Synchronizuje stan z Planfile ticketem (`source.context['delivery']`, `sync['github']`).
  - Wymaga flagi `--apply` do wykonania operacji zdalnych w `run`.
  - Rejestruje transkrypcje wywołań LLM w katalogu `.planfile/gitive-delivery/<run_id>/transcripts`.

---

## Interfejs CLI

```bash
# 1. Jawny import istniejącego GitHub Issue do projektu Planfile
gitive delivery import <projekt> \
  --repo <właściciel/repo> \
  --issue <numer> \
  --file <ścieżka_do_pliku> \
  --accept "Kryterium odbioru" \
  --image <lokalny_obraz_docker> \
  --test '["pytest", "tests/"]'

# 2. Sprawdzenie statusu dostawy i powiązanego PR / testów
gitive delivery status <projekt> --ticket <ticket_id> [--json]

# 3. Uruchomienie cyklu naprawy, testów i publikacji draft PR
gitive delivery run <projekt> --ticket <ticket_id> --apply [--cycles 1..3]
```

---

## Wyniki weryfikacji i testów

Przeprowadzono pełne testy jednostkowe i integracyjne:

1. **`src/gitive/tests/`**: **96 zaliczonych**, 11 pominiętych (środowiskowych noVNC).
   - W tym nowe testy `test_delivery_cli.py`:
     - `ReviewHub` tworzący Draft PR z nagłówkami bezpieczeństwa.
     - Walidacja flagi `--apply`.
     - Struktura statusu i raportu podsumowującego.
     - Rejestracja metadanych dostawy w Planfile i idempotencja importu.
2. **`gpt6/tests_github/`**: **93 zaliczone** (w tym 7 testów `test_selected.py`):
   - Idempotencja importu Issue i odrzucanie sprzecznych zakresów.
   - Odrzucanie zamkniętych Issue, PR jako Issue, fałszywych URL oraz istniejących konkurujących PR.
   - Pętla generacji łatki, utworzenia PR i zaliczenia weryfikacji (`awaiting_review`).
   - Rejestracja niepowodzenia testów i ponawianie próby z informacją zwrotną.
   - Ochrona limitu prób i przekazanie człowiekowi (`needs_human`).
   - Wykrywanie zdalnych modyfikacji (merge, zamknięcie, edycja treści Issue).
   - Odrzucenie już scalonego PR także wtedy, gdy jego opis zawiera zapisane znaki `\\n`.

Test infrastrukturalny `./gitive delivery import doctor-agent --repo semcod/gitive --issue 13 ...`
wykazał, że wcześniejsza wersja błędnie przyjęła Issue #13 mimo istniejącego scalonego PR #14.
Naprawiono detekcję takich PR-ów; po poprawce ten przypadek jest odrzucany przed wywołaniem LLM.

Po ponownym uruchomieniu istniejącego `PLF-006` komenda:

```text
./gitive delivery run doctor-agent --ticket PLF-006 --apply --cycles 1 --json
```

zwróciła `status: needs_human`, `pr: null`, `attempts: 0` i powód
`Issue already has an open/merged PR: 14`. Planfile przeszedł do stanu `blocked`,
a wykonanie zakończyło się bez żądania LLM i bez tworzenia kolejnego PR. To jest
potwierdzony rzeczywisty test deduplikacji na GitHub, nie test atrapy.

---

## Pozostałe ograniczenia i luki wdrożeniowe (Gaps)

1. **Niezależna publikacja / Merge gatekeeper**:
   - Gitive celowo nie wykonuje merge na główną gałąź; lokalne testy w kontenerze są dowodem autora, a scalenie wymaga niezależnego przeglądu człowieka lub workflow CI repozytorium.
2. **Lokalny runtime Docker**:
   - Wykonanie testów w kontenerze wymaga obecności lokalnego obrazu Docker spełniającego wymagania projektu (`sha256:...`).
3. **Zakres edycji plików**:
   - Silnik GPT6 operuje na plikach kodu w dozwolonych ścieżkach (`allowed_paths`); edycje konfiguracji repozytorium lub czystego Markdown wymagają dedykowanych adapterów lub poszerzenia kontraktów napraw.
