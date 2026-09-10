# Terminal projektu: konto i ścieżka PC

```json
{
  "id": "project-terminal-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "verified-and-deployed-local",
  "source_revision": "10152a58738b8a5cdabb29dd412dc163042d7ebe",
  "ticket": "https://github.com/semcod/gitive/issues/5",
  "evidence": ["src/gitive/project_terminal.py", "src/gitive/tests/test_project_terminal.py", "src/gitive/tests/test_workspace.py"]
}
```

## Problem i wynik

Zrzut użytkownika pokazywał terminal `browser` w starej kopii
`/workspace/github/workspaces/doctor-agent`. Osobny kontener projektu miał już
poprawny katalog roboczy, lecz UID 1000 nazywał się `ubuntu`, a HOME był
`/gitive-home`. Wcześniejszy odbiór shellu Gitive nie sprawdzał tego terminala GUI.

Dodano hostową komendę `./gitive twin terminal doctor-agent` oraz pozycję w menu
projektu. Komenda migruje konto runtime na rzeczywiste konto właściciela źródła,
zachowuje poprzedni kontener, tworzy prywatne połączenie SSH i otwiera terminal
na aktywnym pulpicie noVNC. Skrót: **Gitive doctor-agent — tom**.
Nowe runtime również powstają z kontem i HOME właściciela projektu.

Na widocznym terminalu wykonano i sprawdzono:

```text
whoami          → tom
pwd             → /home/tom/github/subactor/doctor-agent
HOME            → /home/tom
python --version → Python 3.13.12
node --version   → v20.19.5
```

UID/GID to 1000:1000. Hostname pozostaje nazwą kontenera. Konto usługi pulpitu
noVNC nadal nazywa się `browser`; powłoka projektu jest odrębnym procesem kontenera
i rzeczywiście działa jako `tom`. Nie zmieniano jedynie wyglądu promptu.

## Weryfikacja

- 79 testów Gitive w kontenerze: wszystkie przeszły, bez pominięć.
- 238 testów doctor-agent w jego kontenerze: wszystkie przeszły po zmianie HOME/konta.
- Odczyt identity przez `docker exec` oraz przez rzeczywiste SSH z noVNC.
- Rzeczywiste okno GUI: zweryfikowano prompt i wyniki powyższych poleceń.
- Próba zapisu do HOME trafiła wyłącznie do prywatnego magazynu; brak pliku na PC.
- Wszystkie bind mounty kontenera pochodzą z katalogu prywatnego workspace.
  Brak trybu privileged, Docker socket i portu SSH publikowanego na hoście.
- Oryginalny checkout `/home/tom/github/subactor/doctor-agent` pozostał czysty.
- Zachowano archiwalną kopię i poprzedni kontener. `workspace resume` nie otwiera
  już starego archiwum jako terminala projektu posiadającego runtime.

Prywatne dowody: `.subactor/recovery/project-terminal/verification.json`.
SHA-256 logów:

| Dowód | SHA-256 |
| --- | --- |
| Gitive | `c7073221fabfb2d4215abb35a8c150bd591714b59ca253bf3b5351e93d92ac0a` |
| doctor-agent | `7fae23930ae5ac9236696413bad6c2358efd94db0f8ed5cd62c6e2a793e85a4f` |
| Zrzut terminala | `b1087284a97db0bd25bb900e09102dcb07a4c4eddb620eede642122c7c551fc4` |

## Zakres i dalsza praca

Ta poprawka zapewnia ręczny terminal właściwego projektu. Nie implementuje P1
automatycznego wykonywania ticketów przez trzy silniki we własnym kontenerze.
Po restarcie kontenera można ponownie otworzyć terminal skrótem; pamięć poprzedniej
sesji nie jest odtwarzana. Klient SSH w noVNC jest instalowany przy pierwszym
wywołaniu komendy; po odtworzeniu obrazu GUI komenda uzupełni go ponownie.

Instrukcja i granice izolacji: [architektura workspace](../information/workspace-project-architecture.md).
Dostarczenie pozostaje osobnym draft PR opartym na PR #4. Lokalny odbiór nie
zastępuje niezależnej zgody na merge; nie wykonano merge ani tagowania wydania.
