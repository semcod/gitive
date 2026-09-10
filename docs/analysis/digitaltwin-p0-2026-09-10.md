# DigitalTwin P0 — wykonanie i weryfikacja

```json
{
  "id": "digitaltwin-p0-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "verified-for-branch-publication",
  "source_revision": "14df7e3fd1199b86c9f949c244bc9402f728f10c",
  "evidence": ["benchmark/runs/20260910T162009Z-digitaltwin-p0/verification.json"]
}
```

## Zakres

Użytkownik potwierdził „gotowe zmiany + następny etap P0”. Dostarczono menu,
Planfile i stan procesów z poprzedniego etapu oraz pełny import wybranego projektu
i runtime, katalog DigitalTwin, testy kontenera i odzyskiwanie migracji.
Zadanie: [Issue #1](https://github.com/semcod/gitive/issues/1), gałąź
`ticket/001-digitaltwin-runtime`. Pierwotne lokalne zmiany zachowano; publikację
przygotowano w osobnym worktree zgodnym z hostowym standardem.

## Wynik próby doctor-agent

- Kontener `gitive-project-doctor-agent-81cc0ca3` działa z prywatnymi mountami.
- Projekt znajduje się wewnątrz pod `/home/tom/github/subactor/doctor-agent`.
- Python **3.13.12**, Node **20.19.5**, Git **2.51.0** potwierdzono w kontenerze.
- Początkowy import obejmował około **20,03 GiB**: cały projekt, Minicondę,
  NVM Node oraz przypięty eksport SKILLS. Następnie dodano pełne prywatne kopie
  editable `skills-agent` i `subllm`. Kolejne plan/prepare wykrywają je automatycznie.
- Testy `doctor-agent`: **238/238** wewnątrz kontenera. Ponowienie zwykłego
  `twin test doctor-agent` również przechodzi. Parametry SKILLS po udanym teście
  zapisano w prywatnym `test-environment.json`, bez publikowania ich jako sekretów.
- Zachowano **PLF-001, PLF-002, PLF-003** i ich istniejące powiązania GitHub.
- Stare kopie projektu oraz poprzednie konfiguracje kontenera pozostały zachowane.
  Rejestr aktywnego projektu wskazuje teraz ścieżkę w nowym workspace.

Początkowe błędy kolekcji testów ujawniły brak kodu instalacji editable poza
venv. Nie instalowano przypadkowych wersji z PyPI i nie zmieniano testów:
rozszerzono kopiowanie o rzeczywiste lokalne zależności. P0 `twin extend` pozwala
uzupełnić środowisko bez ponownego kopiowania Minicondy. Uruchomienia kontenera
po rozszerzeniu zachowują wcześniejszą konfigurację jako zatrzymany backup.

## Bezpieczeństwo danych i granice dowodów

Pełne wybrane drzewa (w tym `.env`, venv i node_modules) porównano po hashach,
trybach i linkach. Mounty projektu/runtime prowadzą wyłącznie do prywatnego
magazynu; źródła PC nie są montowane RW. Runtime prefix jest RO, projekt RW,
HOME osobny. Nie przekazano Docker socketu ani trybu privileged.

Konto GitHub to login odczytany przez hostowe `gh` i referencja do poświadczenia;
nie jest to automatycznie zalogowane konto wewnątrz kontenera projektu. Nie
kopiowano tokenu do obrazu, repo ani publicznego raportu.

Gotowość interpreterów i wynik testów są osobnymi polami. Nie potwierdzamy
odtworzenia wszystkich usług/sterowników/pakietów OS PC. P0 korzysta z obrazu
Ubuntu i pełnych kopii wybranych prefiksów. Wykonywanie napraw trzech silników
w tym kontenerze pozostaje P1; dla projektów po migracji zablokowano cichy fallback
do Pythona aplikacji. Testy uruchamia się przez `twin test`.

## Testy i kompletność publikacji

Pełne `make test` przeszło w kontenerze aplikacji: GLM53, Python/TypeScript GPT6,
Opus5, testy benchmarku oraz **64 testy Gitive**. Osobna próba w nowym kontenerze
projektu daje 238 zaliczonych testów. Testy obejmują brak nadpisania PC, pełny
inventory, konflikty/migrację, brak usuwania obcego kontenera przy błędzie,
przerwanie procesu i jawne blokowanie niewłaściwego runtime.

Weryfikacja w czystym worktree wykryła brak wersjonowania pakietu Planfile oraz
trzech workflow GPT6. Dołączono istniejące pliki wraz z manifestem SHA-256 wheel;
testy zachowały wymagania. Nie aktywowano workflow w głównym `.github` Gitive.

W chronionym wdrożonym rejestrze lokalnego Validatora nie ma `semcod/gitive`.
Push i PR nie oznaczają niezależnego zatwierdzenia ani merge. Nie zmieniano
chronionej polityki, nie wystawiono sztucznych statusów i nie nadano tagu wydania.

## Użycie

```bash
./gitive project open doctor-agent
./gitive twin status doctor-agent
./gitive twin test doctor-agent
./gitive twin exec doctor-agent -- python --version
# Flagi CLI dla exec podaj przed nazwą projektu:
./gitive twin exec --json doctor-agent -- node --version
```

Dla kolejnego projektu: `project new`, potem `twin plan NAZWA` i
`twin prepare NAZWA`. Zależności zewnętrzne można wskazać przez `--include-path`.
`prepare` nie nadpisuje istniejącego workspace; `extend` dodaje nowy prefiks,
`recover` służy tylko do niedokończonej migracji rejestru. Runtime nie jest
zatrzymywany przez `make stop`, które dotyczy kontrolera aplikacji.

[Receipt i hashe prywatnych logów](../../benchmark/runs/20260910T162009Z-digitaltwin-p0/verification.json).
[Architektura](../information/workspace-project-architecture.md) ·
[Plan kolejnego etapu](../refactoring/workspace-delivery.md).
