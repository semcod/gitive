# Matematyka faktów CI/CD i następnego zadania

Uzupełnienie wcześniejszego `MODEL.md`. Wersja GitHub nie udaje, że dowolny log ma skalibrowany model diagnostyczny.

## Obserwacja

Niech obserwacja uruchomienia będzie rekordem:

\[
f_r=(repo, workflow, run\_id, attempt, sha, event, conclusion, jobs, log\_hash, source).
\]

Rozdzielamy dwa fakty: `workflow_result` ze statusem `observed` opisuje metadane GitHub, natomiast `ci_log_excerpt` ze statusem `reported` jest nieufnym tekstem wypisanym przez procesy. Tekst „wszystkie testy przeszły” w stdout nie zastępuje metadanych uruchomienia. Fakt merge jest osobny od faktu dostarczenia wydania.

Klucz obserwacji to `(run_id, attempt)`. Przykładowe identyfikatory: `run:123:1`, `log:123:1`. Dodatkowe migawki źródeł są związane z konkretnym SHA i hashem pliku. Pobierane logi są ograniczonym wycinkiem, nie gwarantowanym kompletnym dowodem całego wykonania.

Hash oczyszczonego fragmentu zapewnia identyfikację bajtów, nie prawdziwość treści. Nie łączymy `head_sha` kontrolera wywołanego przez dispatch z SHA kandydata: ten drugi pochodzi z walidowanego wejścia i tożsamości PR.

## Generowanie i selekcja

\[
\mathcal A_t = Validate(LLM(G, F_t, Source_{sha}, Policy)).
\]

Każda propozycja zawiera tytuł, profil, znane identyfikatory faktów, istniejące dozwolone pliki, uzasadnienie i kryteria odbioru. Nie może zawierać komend, uprawnień ani własnego wyniku oceny.

Przyjęto w tym adapterze:

\[
Score(a)=\widehat p_{k(a)} B_{k(a)}-C_{k(a)}-R_{k(a)},
\qquad \widehat p_k=\frac{\alpha_k}{\alpha_k+\beta_k}.
\]

`B`, `C`, `R` pochodzą z zaufanego profilu konfiguracji. Są przyjętą wspólną skalą użyteczności, nie pomiarem pieniędzy, jakości ani ryzyka. Priorytet pozostaje heurystyką wymagającą oceny na realnych danych.

Oryginalna formuła obejmująca informację pozostaje w modelach v1, natomiast dla logów CI/CD bez zdefiniowanych czułości i prawdopodobieństw wyników przyjmujemy jawnie:

\[
IG(a)=0.
\]

Nie wolno przedstawiać dowolnej pewności modelu jako bayesowskiego prawdopodobieństwa przyczyny awarii. Przyszła diagnostyka może włączyć IG dopiero dla zdefiniowanego eksperymentu i uzasadnionego modelu obserwacji.

## Aktualizacja po testach

Dla dokładnego bieżącego kandydata SHA:

\[
z=\begin{cases}
1 & \text{gdy uruchomiony krok testów i pełna zaufana weryfikacja zakończą się sukcesem},\\
0 & \text{gdy uruchomiony krok testów zakończy się porażką},\\
\varnothing & \text{gdy test nie ruszył, wynik jest anulowany/nieznany lub SHA jest stare.}
\end{cases}
\]

Dla znanego wyniku:

\[
\alpha_k\leftarrow\alpha_k+z,\qquad
\beta_k\leftarrow\beta_k+1-z.
\]

Import faktów może być powtórzony dla nowej próby uruchomienia, lecz aktualizacja licznika dotyczy najwyżej pierwszego przypisanego wyniku danego SHA kandydata. Zapobiega to „uczeniu” wielu niezależnych sukcesów przez powtarzanie tego samego testu.

Nie ma gwarancji niezależności między kolejnymi poprawkami, zadaniami ani wynikami środowiska. Dlatego interpretacja Beta jest roboczym estymatorem przechodzenia ustalonego pipeline'u, a nie eksperymentalnie wykazaną kalibracją. Zmiana modelu, zbioru testów lub trudności zadań może wymagać nowego profilu/okresu oceny.

Sukces testów nie dowodzi jakości refaktoryzacji, braku zmiany zachowania ani poprawności wszystkich kryteriów odbioru. CD może dostarczyć błędną aplikację, jeśli testy nie wykrywają problemu. Dalsza ocena powinna obejmować przegląd człowieka i miary regresji zachowania.

## Stop zamiast produkowania pracy

Wybór jest ograniczony: dozwolone pliki, maksymalny koszt, ryzyko, liczba issues/PR, próby, blokada po awariach i minimalny score. Jeśli zbiór kandydatów jest pusty albo nie ma dopuszczalnego działania, cykl kończy się bez nowego zadania.

Ciągłość oznacza ponowne rozpatrywanie przyszłych faktów i stanu, a nie konieczność ciągłego zmieniania kodu. W stanie równowagi dopuszczalnym wynikiem jest brak refaktoryzacji.
