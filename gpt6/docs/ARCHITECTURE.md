# Architektura GitHub-native

## Cykl zdarzeń

```text
      CI / CD zakończone lub harmonogram / ręczny dispatch
                           |
                   Intuition loop (zaufany)
                           |
            gh API metadane + gh run view logi
                           |
        redakcja -> fakty -> commit intuition-memory
                           |
            LiteLLM -> OpenRouter -> ścisły JSON
                           |
               walidacja -> ranking Python
                           |
       gh issue create -> Git blob/tree/commit/ref -> gh pr create
                           |
          gh workflow run verify-candidate.yml --ref main
                           |
       resolve PR/SHA/pliki -> osobny job testów kandydata
                           |
          zaufany reporter -> status konkretnego SHA
                           |
          workflow_run -> kolejny Intuition loop
                 /                         \
       negatywny test                  pozytywny test
       poprawka <= limit                 oczekiwanie na merge
                                             |
                               ręczny lub chroniony auto-merge
                                             |
                                      CI domyślnej gałęzi
                                             |
                              CD: ZIP + SHA256 -> GitHub Releases
```

## Stan i zdarzenia

`intuition-memory` jest osobną gałęzią bez wspólnego drzewa roboczego z aplikacją. Jej pierwszy commit jest bez rodzica. Następne mają jednego poprzednika.

```text
state.json
  schema_version
  facts[]                    obserwacje, fragmenty logów i migawki kodu
  seen_runs[]                run_id:run_attempt
  tasks{}                    zadania, issues, PR, prepared commit, próby i wyniki
  budgets{UTC-day}            rezerwacje żądań i dostępne liczniki tokenów
  profile_counts{}           alpha i beta dla rodzajów zadań
  consecutive_failures       obwód ograniczający kolejne błędy
  paused_reason
  last_plan_context          identyczny kontekst nie wymusza płatnego planowania
  last_ci_requested_sha
  sequence

events/<sequence>-<uuid>.json
evidence/<sha256>.txt
```

Stan roboczy zawiera maksymalnie 200 najnowszych faktów, 5000 identyfikatorów prób, 100 terminalnych zadań i 90 dni liczników. Starsze informacje pozostają w historii. To kompaktowanie odczytywanego stanu, nie usuwanie danych z Git. Pełne drzewo zdarzeń rośnie; po osiągnięciu limitów API/rozmiaru system zatrzyma się do archiwizacji przez opiekuna.

## Tożsamość i odzyskiwanie

Identyfikator zadania zależy od celu, profilu, zbioru plików i bazowego SHA. Drugi podobnie nazwany pomysł na tych samych plikach nie ustanawia automatycznie nowego problemu. Ta konserwatywna deduplikacja celowo może odrzucić inne zadanie w tym samym obszarze; priorytetem jest ograniczenie spamu.

Przed utworzeniem issue stan zapisuje zadanie. Po awarii między `gh issue create` a zapisem odpowiedzi kolejny proces wyszukuje dokładny marker. Commit poprawki jest niezmienny i zapisany jako `prepared` w pamięci **przed** aktualizacją gałęzi i utworzeniem PR. Gałąź ma nazwę `intuition/issue-N-ID`; ponowienie odzyskuje istniejący PR zamiast generować następny.

Weryfikacja jest wiązana z `pr_number` i `head_sha` w wejściu workflowu oraz jego stałym `run-name`. To SHA kandydata, nie SHA kontrolera w metadanych samego dispatch. Przed raportem sprawdzany jest aktualny stan PR. Raport dla starego kandydata nie zatwierdza nowego SHA. Powtórne uruchomienie testu tego samego SHA zachowuje oddzielne fakty run/attempt, ale nie trenuje licznika drugi raz.

Git Data API odczytuje aktualny ref, tworzy obiekty i przesuwa ref bez `force`. To optymistyczne uzgadnianie, nie serwerowe compare-and-swap z polem expected_old jak w lokalnym `git update-ref`. Równoległe dzieci tego samego rodzica nie mogą oba zostać zaakceptowane jako fast-forward; wyścigi powodują przerwanie, nie nadpisanie. Stała grupa `concurrency` serializuje joby kontrolera w Actions, ale nie proces operatora uruchomiony na laptopie.

Nie wszystkie skutki są transakcyjne: komentarz może nie zostać dopisany po przerwaniu, dispatch może powtórzyć się po utracie potwierdzenia, orphan commit może pozostać w magazynie Git. Nie ogłaszamy semantyki exactly-once dla wszystkich wywołań.

## Statusy zadania

`proposed → ready → verifying → awaiting_merge → completed`

Negatywny wynik `verifying` wraca do `ready` do maksymalnej liczby prób. `needs_human`, `abandoned`, `no_change` zatrzymują to zadanie. Zamknięcie issue bez PR lub zamknięcie niescalonego PR zostaje zauważone. Zewnętrzna modyfikacja gałęzi agenta nie jest nadpisywana. Po pozytywnych testach brak zgody na merge nie wywołuje dalszej poprawki tego samego kandydata.

`needs_human` nie ma automatycznej ścieżki samoodblokowania. Operator analizuje przyczynę, rozstrzyga PR/issue i ewentualnie przygotowuje kolejny zakres pracy. `--reset-circuit` zeruje wyłącznie globalny obwód kolejnych awarii, nie historię zadania ani liczniki kosztowe.

## Kontrola kosztów

Przed każdym żądaniem zapisujemy rezerwację liczby wywołań oraz maksymalnych tokenów odpowiedzi. Jeśli zapis Git się nie powiedzie, żądanie nie zostaje wysłane. Brak odpowiedzi lub awaria modelu nie usuwa rezerwacji. Licznik `actual_tokens` jest diagnostyczny: może nie znać naliczenia timeoutu, a granica doby między rezerwacją i odpowiedzią przypisuje zużycie do doby odbioru. Twarda blokada dotyczy wywołań, nie rachunku USD. Niezależny kredytowy limit klucza OpenRouter jest konieczny przy pracy ciągłej.

## Adaptacja do własnej aplikacji

Edytuj ręcznie `.intuition/config.json`: cel, profile, zakres plików, znane nazwy workflowów i limity. Zastąp lub rozszerz stałe polecenia w `scripts/test_all.py` i CI. Reguła weryfikatora i importer wyniku oczekują stałej nazwy kroku `Run fixed tests with a clean child environment`; zmiana tego kontraktu musi być spójna.

Agent nie tworzy nowych plików, nie usuwa ich, nie zmienia zależności, nie edytuje testów, workflowów, własnego kontrolera ani polityk. Jest to świadomie ograniczona refaktoryzacja istniejącego kodu. Instalacja zależności aplikacji wymagającej innych runtime'ów wymaga zaufanej konfiguracji joba; nie należy pobierać poleceń instalacyjnych z propozycji LLM.

CD jest konkretnym przykładem continuous delivery w ekosystemie GitHub. Nie zawiera danych serwera PHP/Plesk, hasła SSH, klastra Kubernetes ani automatycznej migracji produkcyjnej bazy. Włączenie takiego deploymentu wymaga osobnej, zatwierdzonej polityki, sekretów i kryteriów sukcesu.
