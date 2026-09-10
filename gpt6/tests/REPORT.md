# Raport wykonanych testów

Data: 10 września 2026 r. Środowisko Linux; Python 3.13.5, Node.js 22.16.0, Git 2.47.3. TypeScript uruchomiony z `--experimental-strip-types`. Kompilator użyty do dodatkowej kontroli statycznej: TypeScript 5.8.3.

| Badanie | Wynik |
|---|---|
| Python unittest | 25/25 zaliczonych |
| Node test runner | 25/25 zaliczonych |
| EIG — 1000 przypadków, generator Random(20260910) | Zgodność przy tolerancji bezwzględnej/względnej 1e-12 |
| Maksymalna różnica EIG między językami | 2.220446049250313e-16 |
| Pełny CLI: init → prompt → plan → observe → prompt → plan, Python | Zaliczony; wybór T1, potem T2; cztery zaakceptowane commity |
| Ten sam obieg CLI, TypeScript | Zaliczony; wybór T1, potem T2; cztery zaakceptowane commity |
| Odrzucenie odpowiedzi dla starego commitu | Zaliczony w obu obiegach |
| Zapis Git z nieaktualną bazą | Odrzucony w obu zestawach testów |
| Statyczna kontrola TypeScript | tsc --noEmit --strict; kod wyjścia 0 |

Dodatkowa kontrola statyczna używała ES2023, NodeNext, allowImportingTsExtensions i dostępnych w środowisku deklaracji typów Node. Kompilator i deklaracje nie są zależnościami wykonawczymi paczki i nie są dołączone.

Testy jednostkowe obejmują entropię, test idealny i bezinformacyjny, granice EIG, aktualizację Bayesa, zdarzenie niemożliwe, niepoprawne liczby, brak mutacji wejścia, zmianę priorytetu po obserwacji, rozróżnienie awarii diagnostyki od obalenia hipotezy, zablokowane zależności po niepowodzeniu, nieznane fakty/zależności, cykle, niedozwolone pola odpowiedzi modelu, duplikaty, budżet, limit ryzyka, próg zatrzymania, ponowne użycie dowodu, stan oczekujący, stabilny hash Unicode oraz integralność historii Git.

**Nie zbadano:** jakości propozycji rzeczywistego LLM, empirycznej kalibracji parametrów, reprezentatywnej wydajności/ceny, dużych repozytoriów, wielu hipotez, driftu danych, izolacji wykonywania kodu, systemów Windows/macOS ani innych wersji środowisk. Dane i obserwacje są jawnymi przykładami syntetycznymi. Wyniki nie są benchmarkiem „intuicji” człowieka ani modeli językowych.

Surowe logi i wynik crosscheck znajdują się w katalogu `results/`. Skrypt `crosscheck.py` uruchamia oba środowiska tylko dla porównania; docelowy program może używać jednego języka.
