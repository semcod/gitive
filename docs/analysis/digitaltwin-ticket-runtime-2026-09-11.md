# Wykonanie ticketów w runtime DigitalTwin

```json
{
  "id": "digitaltwin-ticket-runtime-2026-09-11",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-11",
  "owner": "semcod/gitive",
  "status": "implemented-and-tested",
  "ticket": "https://github.com/semcod/gitive/issues/20",
  "evidence": [
    "src/gitive/runtime_develop.py",
    "src/gitive/jobs.py",
    "src/gitive/control.py",
    "src/gitive/tests/test_runtime_develop.py",
    "src/gitive/tests/test_jobs.py"
  ]
}
```

## Problem

`project run` odrzucał każdy projekt z `workspace_ref`. W efekcie ticket
`doctor-agent` można było zapisać i zsynchronizować z GitHubem, ale nie można
było rozpocząć jego realizacji. Panel WWW pokazywał taki projekt jako trwale
zablokowany, nawet gdy kontener DigitalTwin działał.

Drugim ryzykiem byłoby obejście blokady przez uruchomienie testów na hoście.
To naruszałoby założenie, że projekt korzysta z prywatnego, skopiowanego
środowiska Pythona/Node i własnej ścieżki użytkownika.

## Zmiana

Dodano `runtime_develop.py`. Worker sprawdza katalog prywatnego rootfs i jego
repozytorium Git, deleguje komendę akceptacyjną przez `DigitalTwin.execute`
(czyli do `docker exec` w kontenerze projektu), a propozycję poprawki wykonuje
w tymczasowym prywatnym klonie. Zapisuje transkrypty LiteLLM, kopiuje wyłącznie
zatwierdzone edycje do checkoutu DigitalTwin, ponownie uruchamia testy w
kontenerze i zachowuje commit tylko po sukcesie. Przy nieudanym teście pliki
są przywracane, a wynik ma status `rejected`.

`jobs.start()` wybiera ten worker dla projektu z `workspace_ref` i odmawia
startu tylko wtedy, gdy kontener nie działa. `control.dashboard()` zgłasza
blokadę tylko dla niedziałającego runtime, a nie dla każdego projektu
DigitalTwin.

## Granice autonomii

Zmiana uruchamia wykonanie lokalnego ticketu w runtime i nie nadaje Gitive
uprawnień do samodzielnego merge. Publikacja GitHub nadal wymaga jawnego
importu Issue, utworzenia draft PR przez `gitive delivery` oraz niezależnego
gatekeepera. Workflow `doctor-agent` pozostaje domyślnie w trybie dry-run; do
harmonogramu trzeba jawnie włączyć `AUTONOMOUS_DOCTOR_WRITES` i
`AUTONOMOUS_ISSUE_INTAKE_ENABLED` po przeglądzie polityki repozytorium.

## Weryfikacja

- `PYTHONPATH=src python3 -m unittest src.gitive.tests.test_jobs -v` — 4/4.
- `PYTHONPATH=src python3 -m unittest discover -s src/gitive/tests -v` — pełny
  zestaw przechodzi; testy wymagające lokalnego `age` pozostają pominięte.
- Test runtime potwierdza, że komenda akceptacyjna jest wywoływana przez
  `DigitalTwin.execute`, a nie przez `subprocess` na hoście.

## Następny krok operacyjny

Po wdrożeniu uruchomić kontener projektu (`gitive twin status doctor-agent`),
wybrać ticket Planfile i użyć `gitive tickets run doctor-agent --ticket PLF-…`.
Wynik `repaired` oznacza zatwierdzony commit w prywatnym runtime; przed
publikacją trzeba wykonać synchronizację ticketu i jawny cykl `gitive delivery`.
