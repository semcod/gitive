# Intuition–Git: model wyboru następnego zadania

Dwie referencyjne implementacje tego samego planera: Python oraz TypeScript/Node.js.
Do uruchomienia wybranej wersji potrzebujesz tylko jej środowiska wykonawczego i Git.
LLM jest źródłem propozycji przez interfejs JSON — nie ma zależności od konkretnego dostawcy, SDK, bazy danych ani frameworka agentowego.

**Zakres:** generowanie kontraktu wejściowego dla LLM, przyjęcie propozycji, walidacja, ranking, zapis decyzji w Git, import zatwierdzonej obserwacji i aktualizacja przekonań. Pakiet nie wykonuje kodu zaproponowanego przez model i nie zawiera klienta konkretnego API LLM. Przykłady i testy używają danych syntetycznych, nie odpowiedzi uzyskanych w tym badaniu od rzeczywistego LLM.

## Uruchomienie wybranej wersji

Polecenia wykonuj z katalogu głównego paczki. `memory.git` musi być nową ścieżką; init nie nadpisuje istniejących repozytoriów.

### Python

Kod wykorzystuje składnię dostępną w Pythonie 3.11+; wykonane testy: Python 3.13.5.

```sh
python python/cli.py init memory.git examples/state.json
python python/cli.py prompt memory.git > request.json
```

Przekaż zawartość `request.json` wybranemu LLM. Zapisz odpowiedź jako `reply.json`. Oczekiwany format:

```json
{
  "base_commit": "DOKLADNY_HASH_Z_REQUEST_JSON",
  "tasks": [
    {
      "id": "T1",
      "title": "Zweryfikuj hipotezę H1 kontrolowanym restartem",
      "profile": "diagnose_cache",
      "facts": ["F1", "F2"],
      "depends_on": [],
      "acceptance": "Zatwierdzony test daje interpretowalny wynik dodatni albo ujemny."
    }
  ]
}
```

Identyfikatory są ograniczone do ASCII; opisy mogą być po polsku. Puste `tasks` oznacza brak uzasadnionych propozycji. Propozycja może zawierać najwyżej osiem zadań. Model nie może dopisywać `score`, `command` ani nowych profili uprawnień. Nieznane fakty/profil, nieznana zależność, cykl albo nieaktualny commit powodują odrzucenie.

```sh
python python/cli.py plan memory.git reply.json
```

Wyjście zawiera ranking i hash nowego commitu. Wybranie zadania NIE uruchamia go. Zaufany operator albo wcześniej zatwierdzony wykonawca przeprowadza zadanie i sprawdza kryterium odbioru. Obserwację zapisz w `observation.json`:

```json
{
  "base_commit": "DOKLADNY_HASH_Z_ODPOWIEDZI_PLAN",
  "event": {
    "event_id": "E1",
    "task_id": "T1",
    "success": true,
    "positive": true,
    "summary": "Opis rzeczywistego, sprawdzonego wyniku diagnostyki."
  }
}
```

`success=true` oznacza osiągnięcie kryterium danego zadania. Dla diagnostyki jest to uzyskanie użytecznego pomiaru, NIE potwierdzenie hipotezy. `positive` opisuje kierunek wyniku diagnostycznego. Przy nieudanym zadaniu lub zadaniu niediagnostycznym `positive` musi być `null`. Wynik nieznany nie jest porażką — nie należy importować go jako `success=false`.

```sh
python python/cli.py observe memory.git observation.json approved-test-output.txt
python python/cli.py prompt memory.git > next-request.json
```

`approved-test-output.txt` to rzeczywisty plik z dowodem. Jego SHA-256 i bajty są zapisywane w historii Git. Sama obecność pliku nie dowodzi poprawności interpretacji. Dlatego importowany opis ma status `reported`, a nie automatycznie `observed`. Aktualizacja Bayesowska zakłada, że operator prawidłowo zatwierdził pomiar i jego model.

### TypeScript

Te same polecenia i kontrakty; zamiast `python python/cli.py` użyj:

```sh
node typescript/cli.ts init memory-ts.git examples/state.json
node typescript/cli.ts prompt memory-ts.git > request-ts.json
```

Dla testowanego Node.js 22.16.0 potrzebna jest flaga:

```sh
node --experimental-strip-types typescript/cli.ts init memory-ts.git examples/state.json
```

Dokumentacja Node wskazuje stabilność type stripping od 24.12.0/25.2.0. W tym badaniu wykonano testy tylko na 22.16.0, z flagą. Używana jest wyłącznie usuwalna składnia TypeScript. Nie ma zależności npm ani etapu budowania. Samo uruchomienie `.ts` NIE sprawdza typów; walidacja JSON działa jawnie w czasie wykonania. Statyczną kontrolę przeprowadzono osobno dostępnym kompilatorem — zobacz `tests/REPORT.md`.

## Odczyt pamięci

Repozytorium jest lokalne i bare. Nie dotyka plików roboczych aplikacji.

```sh
git --git-dir=memory.git log refs/heads/memory --oneline
git --git-dir=memory.git show refs/heads/memory:state.json
git --git-dir=memory.git show refs/heads/memory:last-event.json
```

Drzewo zawiera `state.json`, `last-event.json` i zaimportowane pliki `evidence/<sha256>.bin`. W każdym commicie `last-event.json` oznacza inne zdarzenie; wcześniejsze wersje są w historii. Stan początkowy odwołuje się do raportu z `examples/report.txt` w tej paczce. Nie importujemy automatycznie dowolnych ścieżek wymienionych w danych.

Zapisy wykorzystują prywatny indeks, `hash-object`, `write-tree`, `commit-tree` i `update-ref` z oczekiwanym poprzednim hashem. Nieaktualny zapis przegrywa zamiast nadpisywać nowszy stan. Nieudany zapis może pozostawić nieosiągalne obiekty Git, ale nie zmienia zaakceptowanej gałęzi.

Git zapewnia historię treści, nie prawdziwość danych, poufność ani sandbox. Administrator może przepisać historię. Używaj własnego, zaufanego repozytorium i zaufanego programu Git. Nie zapisuj kluczy dostępowych ani sekretów.

## Testy

Wystarczy uruchomić testy wybranego języka:

```sh
python -m unittest discover -s python -p 'test_*.py' -v
node --experimental-strip-types --test typescript/test-engine.ts
```

Porównanie obu implementacji wymaga obu środowisk, ale jest narzędziem badawczym, nie zależnością wdrożeniową:

```sh
python tests/crosscheck.py
```

Porównuje 1000 deterministycznie wylosowanych parametrów EIG, ranking i dwa pełne obiegi CLI/Git. Ten obieg korzysta z zapisanych propozycji przykładowych, nie z wywołania LLM.

## Parametry, założenia i granice

Wszystkie liczby w przykładzie — priory, czułość, odsetek wyników fałszywie dodatnich, pseudoliczności Beta, wartość, koszt i ryzyko — są demonstracyjne. To NIE kalibracja empiryczna. H1 jest hipotezą o przyczynie, nie zaobserwowanym faktem.

LLM wybiera profile z zaufanego słownika, ale ich nie zmienia. Nowy profil wymaga decyzji operatora oraz własnego kryterium odbioru i oszacowania parametrów. `allowed` jest bramką planowania, nie mechanizmem izolacji procesu ani zgodą na dowolny kod o podobnym tytule. Semantyka zadania musi odpowiadać profilowi; kontrola identyfikatorów tego nie dowodzi.

Model jest binarny i krótkowzroczny. Zakłada wiarygodność modelu obserwacji oraz, w aktualizacjach kolejnych pomiarów, odpowiednią niezależność warunkową. Nie modeluje automatycznie korelacji źródeł, dryfu rozkładu, wielu przyczyn ani awarii testu zależnej od H1. Odrzucenie identycznego hasha dowodu nie wykrywa wszystkich przypadków ponownego wykorzystania tej samej informacji.

Klucz duplikatu obejmuje cel, profil i zestaw faktów, nie tytuł. To konserwatywna heurystyka: różne metody badania powinny mieć różne profile. Nowy fakt może uzasadnić kolejne zadanie podobnego typu. Powtórzony dowód o innych bajtach nie staje się przez to niezależny.

Nie ma automatycznego wykonywania zadań, wykonywania tekstu LLM w powłoce, klienta HTTP/SDK, kalibratora danych historycznych, liczników opłat/tokenów LLM ani selekcji kontekstu dla dużej historii. `budget` i `cost` używają wspólnych umownych jednostek demonstracyjnych. Przed wdrożeniem oddziel koszty decyzyjne od budżetu czasu i wywołań, dodaj obsługę anulowania zadania oczekującego i jawny limit iteracji. Dla większych zbiorów zastąp wysyłanie całego stanu wyborem istotnych faktów i odnośników do źródeł.

Pliki `MODEL.md` i `SOURCES.md` wyjaśniają model oraz podstawy porównania języków.
