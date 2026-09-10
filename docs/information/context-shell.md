# Shell projektu, ticketu i operacji

```json
{
  "id": "context-shell",
  "kind": "information",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "verified-and-deployed-local",
  "source_revision": "50093fdffa8903e83c522813f89fbcdef209cd02",
  "ticket": "https://github.com/semcod/gitive/issues/3",
  "evidence": ["src/gitive/tests/test_shell.py", "src/gitive/tests/test_operations.py", "src/gitive/tests/test_develop.py"]
}
```

## Użycie

Uruchom `./gitive shell`. Wpisz `projects` (lub wybierz „Wybierz projekt” z menu),
następnie numer projektu. Wpisz `tickets`, następnie numer ticketu z listy
zawierającej tytuł, status, wykonawcę, datę i czas Europe/Warsaw oraz Issue GitHub.
Identyfikator wybieranego ticketu jest rozwiązywany automatycznie.

Przykład po wybraniu istniejącej próby synchronizacji:

```text
tom/doctor-agent/PLF-001/idle>
```

Pierwszy segment jest nazwą lokalnego użytkownika uruchamiającego shell,
nie właścicielem repozytorium GitHub. Dla UID bez wpisu w kontenerze: `uid-1000`.
Brak wybranego projektu lub ticketu oznacza `-`.

| Polecenie w shellu | Działanie |
| --- | --- |
| `projects` | Wybór projektu |
| `tickets` | Wybór lokalnego ticketu Planfile |
| `new` | Tytuł, opis, wybór auto / GLM53 / GPT6 / Opus5 |
| `status` | Status wybranego ticketu, adres Issue, aktualna operacja i PID |
| `run` | Uruchomienie wybranego ticketu przypisanym wykonawcą |
| `sync pull` | Odczyt zmian powiązanego Issue z GitHub |
| `sync push` | Publikacja/aktualizacja wybranego ticketu; pierwsza wymaga owner/repo |
| `operations` | Ostatnie 20 zdarzeń tego ticketu w bieżącym uruchomieniu |
| `watch` | Obserwacja zmian; Ctrl+C wraca do shellu bez zatrzymania pracy |
| `stop` | Zatrzymanie pętli tylko wybranego projektu |
| `back` lub `0` | Ticket → projekt → Gitive |
| `menu`, `help`, `exit` | Działania w kontekście, pomoc, wyjście |

Pełne komendy CLI nadal działają, np. `workspace status` lub `twin test doctor-agent`.
`sync` bez wybranego ticketu pokazuje instrukcję PC → noVNC. Synchronizacja
workspace jest osobną komendą `workspace resync`.

## Skąd pochodzą tickety doctor-agent

Lista pochodzi z natywnego Store Planfile w prywatnej kopii projektu, filtruje
sprint `gitive` i `source.tool=gitive`. Nie jest wynikiem `gh issue list` ani
automatycznym importem wszystkich zgłoszeń GitHub.

| Lokalny ticket | Wykonawca | Powiązane Issue |
| --- | --- | --- |
| PLF-001 | GLM53 | [#407](https://github.com/subactor/doctor-agent/issues/407) |
| PLF-002 | GPT6 | [#408](https://github.com/subactor/doctor-agent/issues/408) |
| PLF-003 | Opus5 | [#409](https://github.com/subactor/doctor-agent/issues/409) |

Te trzy próby utworzono lokalnie, wysłano do GitHub i sprawdzono synchronizację
powrotną/stanu zgodnie z [raportem integracji](../analysis/planfile-doctor-agent-2026-09-10.md).
Sam stan `done` nie potwierdza wykonania kodowania przez LLM.
Planfile używa API GitHub; uwierzytelnienie pochodzi z GH_TOKEN/GITHUB_TOKEN lub
wyniku lokalnego `gh auth token` przechowywanego tylko w pamięci.

## Rejestr operacji i zakres

`develop.py` zapisuje prywatne `operations.jsonl` oraz atomowy `operation.json`
w katalogu `LOOP_DATA/<run>/develop-<iteration>/`. Każdy wpis zawiera projekt,
ticket, wykonawcę, run ID, PID kontenera, kolejność, czas UTC, operację i funkcję.
Rejestr nie zawiera argumentów funkcji, treści kodu, promptów ani credentiali.
Pełne zapisy LLM pozostają w osobnym istniejącym rejestrze transcripts.

Obserwator przechwytuje wejście/wyjście z wybranych funkcji rzeczywiście
załadowanego silnika (rozróżnienie GLM53 i Opus5 po ścieżce kodu, pomimo wspólnej
nazwy pakietu `intuition`). Przykłady: `glm53.core.choose`, `gpt6.llm.complete`,
`opus5.repair.repair`, natywne testy i wywołania Git. Kontroler osobno oznacza
testy bazowe/końcowe, czytanie wyników, walidację oraz zapis poprawki.

`planning`, `scoring`, `log-reading`, `coding`, `validation`, `tests`, `commit`,
`fetch`, `merge`, `learning` opisują wykonywaną funkcję. `repair` i `preparing`
oznaczają szerszy zakres, gdy nie trwa rozpoznana funkcja wewnętrzna.
Commit może zapisywać pamięć silnika; `merge` w tym lokalnym adapterze to
fast-forward prywatnej kopii kodu, nie merge PR na GitHub.

Serwer `GET /api/operations?project=...&ticket=...` wiąże zdarzenie z aktualnym
projektem, ticketem, wykonawcą, run ID i PID żywego procesu. Po zakończeniu
zwraca `idle`, po restarcie `interrupted`. Dla aktywnego wykonania bez zgodnego
zdarzenia zwraca `unknown`. Klient przy utracie połączenia pokazuje `offline`.
Przypisanie ticketu do narzędzia nie wystarcza do pokazania operacji `coding`.

W terminalu prompt-toolkit odświeża prompt co sekundę, zachowując wpisywany tekst.
Szybkie operacje mogą zakończyć się pomiędzy odświeżeniami: pozostają w `operations`.
Bez prompt-toolkit lub przy przekierowanym stdin prompt odświeża się po komendzie.
Wybór kontekstu trwa przez sesję shellu; ponowne uruchomienie wymaga wyboru z listy.
Wyjście z shellu nie kończy uruchomionej wcześniej pętli.

Instrumentacja obejmuje trzy adaptery **uruchamiane przez Gitive development**.
Samodzielnie uruchomiony silnik oraz osobna pętla benchmarku nie stają się
automatycznie procesami wybranego ticketu. Historyczne logi nie są uzupełniane
fikcyjnymi operacjami. Podłączenie silników do kontenera P0 doctor-agent nadal
wymaga P1: `run` zgłosi ten brak, a `twin test doctor-agent` wykonuje testy
we właściwym środowisku.

## Weryfikacja

`make test-loop` sprawdza wybór numerami i powrót, powiązanie synchronizacji,
odświeżanie operacji, utratę połączenia i ochronę przed pokazaniem procesu innego
projektu. Testy operacji obejmują martwy PID, restart, uszkodzony zapis i
przywrócenie wcześniejszego profilera. Test integracyjny wykonuje rzeczywiste
planowanie, walidację, testy i commity trzech natywnych adapterów w tymczasowych
repozytoriach z kontrolowanymi odpowiedziami SDK. Nie wymaga płatnego LLM.

Wynik odbioru: **74 testy bez pominięć**, wdrożony serwer i lokalny CLI.
[Raport wykonania](../analysis/context-shell-2026-09-10.md).
