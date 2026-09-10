# Planfile i import workspace PC do Gitive noVNC

```json
{
  "id": "planfile-doctor-agent-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "verified-local-not-published",
  "source_revision": "14df7e3fd1199b86c9f949c244bc9402f728f10c",
  "evidence": ["benchmark/runs/20260910T153910Z-planfile-doctor-agent/verification.json", "src/gitive/planfile_bridge.py", "src/gitive/novnc_workspace.py"]
}
```

## Zakres

Raport dotyczy adaptera Gitive, importu jego workspace oraz próby integracyjnej
na prywatnej kopii doctor-agent. Nie jest audytem całej floty subactor ani nowym
benchmarkiem jakości odpowiedzi LLM. Kod źródłowy doctor-agent na PC nie został
zmieniony; nie wykonano publikacji kodu.

## Wykonane czynności i dowody

### Workspace PC → prywatne noVNC

Po zamknięciu pozostałych aplikacji przez użytkownika wykonano komendy Gitive:

```bash
./gitive workspace snapshot nvidia-doctor-agent --project subactor/doctor-agent \
  --browser all --include-sessions --exclude-session .codex \
  --exclude-session .config/Code/User --exclude-session .config/Cursor/User
./gitive workspace clone
./gitive workspace activate --browser firefox --include-sessions
./gitive workspace activate --browser chrome
./gitive workspace resync --include-sessions --dry-run
./gitive workspace resync --include-sessions --apply
```

Clone i activate pozwalają wybrać zapis z listy. W wykonanej próbie wskazano
jednoznaczne ID z receipt. Snapshot `nvidia-doctor-agent-20260910T152603Z-d0b4a3`
i clone `2db1d474b3534ed4b667f277e53cab5b` zakończyły się poprawnie.

Skopiowano `.claude`, `.continue`, konfigurację subactor-shell, historię Bash,
Chrome, Chromium i rzeczywisty profil Firefox ze Snap. Aktywna `.codex` została
wyłączona. Profile IDE wyłączono z tej próby: Cursor zajmował około 28 GB,
Code około 4,4 GB. Pierwszy import z tymi katalogami zatrzymano; usunięto tylko
jego własny katalog roboczy. Nie usunięto danych PC.

W noVNC softreck aktywowano Firefox 155.0.1 i Google Chrome 152.0.7977.82.
Zainstalowane prywatnie binaria mają te same wersje co PC; wersję sprawdzono
poleceniem `--version`, a następnie potwierdzono uruchomione procesy GUI.
Firefox został uruchomiony z menedżerem profili. Chromium pozostaje w archiwum.
Nie potwierdzono zalogowania do serwisów: zaszyfrowane cookies i systemowy
keyring mogą wymagać ponownego logowania.

Nowe skróty `gitive-pc-firefox.desktop` i `gitive-pc-chrome.desktop` zawierają
datę i godzinę importu. Poprzednie profile zachowano pod prywatnym
`~/.local/share/gitive-isolated/desktop-backups/`. Aktywacja zatrzymuje tylko
kontener pulpitu, ma blokadę równoległego wykonania i wycofuje podmianę profili
przy błędzie. Nie kopiuje pamięci procesów ani aktywnej rozmowy Codex.

Dodatkowo prywatna kopia binarnego Claude Code 2.1.266 działa pod
`/home/browser/.local/bin/claude`. Systemowy `/usr/local/bin/claude` nadal ma
wersję 2.1.228; do użycia skopiowanej wersji podaj pełną ścieżkę. Kopia katalogu
klienta nie stanowi dowodu sprawnego logowania ani kompletnej instalacji IDE.

Resync wykrył sześć zmian w sesjach Claude i zero konfliktów. Późniejszy `--apply`
został zablokowany kontrolą „Stan zmienił się podczas synchronizacji”; nie zapisano
tej aktualizacji. Poprzednia kopia pozostaje zachowana. Osobny późniejszy podgląd
projektu wykazał 171 zmian, m.in. nowe metadane Git i worktree
`ticket-410--strict-profile-configuration` utworzone poza tą operacją. Nie
podmieniano działającego repo ani tego worktree. Resync aktualizuje kopię
offline; nie nadpisuje automatycznie otwartych profili pulpitu. Ponowna aktywacja
jest osobnym, jawnym krokiem. Snapshot pomija katalogi zależności i cache według
obecnej listy wykluczeń; nie jest pełnym obrazem środowiska PC.

Audyt bind mountów noVNC potwierdził zapis wyłącznie wewnątrz prywatnego magazynu.
Oryginały PC dostępne są aplikacji jedynie do odczytu. Nie udostępniono Docker
socketu kontenerowi aplikacji ani pulpitu.

### Tickety per projekt: semcod/planfile

Dostarczono wspólny `planfile_bridge.py`, używający natywnego Store oraz modeli
Planfile. `.planfile` jest magazynem ticketów wewnątrz prywatnego repo projektu.
`jobs.py` zakłada ticket przed uruchomieniem wybranego GLM53, GPT6 lub Opus5
oraz zapisuje wynik. Sam sukces naprawy oznacza oczekiwanie na weryfikację,
a nie zgodę na merge.

Planfile 0.1.124 zbudowano z lokalnego źródła o zaobserwowanym HEAD
`40dbf7164fdebf62247c8609e838fa8941749492`; manifest wheel zawiera SHA-256.
Obraz aplikacji otrzymał Git 2.51.0, ponieważ wcześniejszy Git 2.39 nie obsługiwał
rozszerzenia relativeworktrees repo doctor-agent.

Pierwszy rzeczywisty projekt zarejestrowano jako `doctor-agent`. Wcześniejszy
wpis `copy-only-check` pozostaje testem. Aktywna kopia projektu leży pod
`~/.local/share/gitive-isolated/github/projects/doctor-agent`; import workspace
utworzył osobną kopię `github/workspaces/doctor-agent`. Nie wykonano automatycznej
migracji między tymi katalogami ani provisioningu osobnego kontenera projektu.

| Wykonawca przypisany do ticketu | Lokalny ticket | Rzeczywiste Issue | Wynik |
| --- | --- | --- | --- |
| GLM53 | PLF-001 | [407](https://github.com/subactor/doctor-agent/issues/407) | create, ponowny push bez duplikatu, zmiana tytułu i zamknięcie na GitHub → pull lokalny |
| GPT6 | PLF-002 | [408](https://github.com/subactor/doctor-agent/issues/408) | create, idempotentny retry, lokalne done → zamknięcie GitHub |
| Opus5 | PLF-003 | [409](https://github.com/subactor/doctor-agent/issues/409) | create, idempotentny retry, lokalne done → zamknięcie GitHub |

Wszystkie trzy Issue testowe są zamknięte. Powiązania lokalne zachowują numer,
URL, repo oraz skróty treści do wykrywania konfliktów. Token pobierany jest przez
lokalne `gh auth token` wyłącznie do pamięci; nie trafia do raportu ani konfiguracji.
Synchronizacja wymaga jawnego `gitive tickets sync`. Bezpośrednie CLI trzech
silników, uruchomione poza Gitive, nie przechodzą przez ten adapter.

## Weryfikacja

- Gitive: **50 testów zaliczonych**, w tym Planfile, konflikty synchronizacji,
  aktywacja z zachowaniem poprzedniego profilu i resync Firefoksa Snap.
- Doctor-agent: **238 testów zaliczonych** na prywatnej kopii kodu. Użyto lokalnego
  interpretera Python 3.13 z istniejącego venv, bez zapisu bytecode do źródła.
- Początkowe błędy testów doctor-agent wynikały z braku przypiętego SKILLS.
  Dostarczono prywatny eksport Git skills-agent z commit
  `2df2eec7abd49d5db98a6ef0dc3d8e7fbedca22d` i ustawiono wymagane ROOT/REF/SHA.
  Nie maskowano tego błędu modyfikacją testów lub źródła produktu.
- Oryginalny doctor-agent: `git status --short` pusty po wykonanych pracach.
- [Receipt z hashami prywatnych logów](../../benchmark/runs/20260910T153910Z-planfile-doctor-agent/verification.json).

## Ograniczenia i następne kroki

1. Provisioning osobnego kontenera projektu, identyczne ścieżki oraz dokładne
   wersje Python/Node/zależności pozostają do wdrożenia. Obecna kopia nie spełnia
   jeszcze wymagania pełnego klona środowiska PC.
2. Ujednolicić rejestr projektu i workspace, zachowując lokalne tickety oraz
   rozróżnienie źródła PC, kopii offline i aktywnego pulpitu.
3. Zautomatyzować przygotowanie zgodnych binariów przeglądarek i rozszerzyć
   formularze WWW o aktywację przez kontrolowany adapter hosta.
4. Przeprowadzić oddzielną próbę rzeczywistej naprawy LLM → testów konkretnego SHA
   → PR → niezależnego walidatora → kontrolowanego merge. W tej próbie nie
   tworzono PR, nie scalano kodu i nie nadawano tagów wydania.

Dokument i kod pozostają lokalnymi zmianami. Nie wykonano commit, PR ani merge
Gitive w ramach tej weryfikacji.
