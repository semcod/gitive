# Matematyczny model „intuicji”

To propozycja inżynierska, nie model neurologiczny ani potwierdzona teoria ludzkiej intuicji. Intuicję definiujemy operacyjnie jako szybkie proponowanie obiecujących następnych działań w niepełnie znanym stanie projektu.

## Stan i generator

Stan S_t = (G, F_t, H_t, A_t, D_t, B_t) obejmuje cel, zapisane obserwacje i twierdzenia, hipotezy, zadania, doświadczenia oraz budżet. Każde twierdzenie zachowuje źródło i status: observed, reported albo disputed. Hipoteza nigdy nie staje się faktem tylko dlatego, że model nadał jej wysoką pewność.

Zestaw kandydatów:

    candidates_t = Validate(LLM_theta(Context(S_t)))

LLM odpowiada za rozpoznanie wzorców i proponowanie zadań. Kontroler odpowiada za sprawdzenie referencji, zależności, uprawnień, budżetu i ranking. Wagi LLM theta nie są zmieniane; uczą się pamięć kontekstowa i jawne parametry planera.

Zadanie a posiada profil działania, odwołania do faktów i kryterium odbioru. Nowy profil zaproponowany przez LLM nie może automatycznie uzyskać uprawnień ani wiarygodnych parametrów liczbowych.

## Przekonania i informacja

Dla hipotezy binarnej H:

    p = P(H | F)
    s = P(Y=+ | H, a)
    f = P(Y=+ | not H, a)
    q = p*s + (1-p)*f

Aktualizacja po wyniku dodatnim:

    P(H | Y=+) = p*s / (p*s + (1-p)*f)

Po wyniku ujemnym:

    P(H | Y=-) = p*(1-s) / (p*(1-s) + (1-p)*(1-f))

Zerowy mianownik oznacza obserwację niemożliwą w zadeklarowanym modelu. Wtedy nie zwracamy arbitralnego prioru, lecz błąd wymagający przeglądu modelu.

Entropia binarna w bitach:

    h(p) = -p*log2(p) - (1-p)*log2(1-p), h(0)=h(1)=0

Oczekiwana informacja z użytecznego wyniku:

    I(a) = h(q) - p*h(s) - (1-p)*h(f)

Jest to równoważne h(p) minus oczekiwana entropia posterioru. Doskonały test daje h(p) bitów, test z s=f daje zero. Jest to informacja o zadeklarowanej hipotezie, nie liczba nowych słów wygenerowanych przez model.

## Zdolność wykonania i użyteczność

Dla profilu k modelujemy prawdopodobieństwo osiągnięcia wcześniej określonego kryterium odbioru:

    p_k ~ Beta(alpha_k, beta_k)
    E[p_k] = alpha_k / (alpha_k + beta_k)

Po zweryfikowanym wyniku z=1 albo z=0:

    alpha_k <- alpha_k + z
    beta_k  <- beta_k + 1-z

Przy diagnostyce z=1 oznacza uzyskanie użytecznego wyniku, także wyniku obalającego hipotezę. Nieznany wynik nie jest z=0. Ta agregacja zakłada porównywalność prób; przy zmianie trudności, typu zadania lub modelu należy rozważyć nowy profil albo osobne parametry.

Nie należy mylić p_k z p=P(H|F): pierwsze opisuje zdolność wykonania zadania, drugie prawdopodobieństwo hipotezy o świecie.

Niech V(a) będzie wartością poprawnego skutku. W przykładzie poprawka nakierowana na H1 ma relewancję r(a)=P(H1|F); przy działaniach bez takiego warunku r(a)=1. Korzyść warunkowa wynosi G(a)=V(a)*r(a).

Używany w kodzie ranking:

    Score(a) = p_k * (G(a) + lambda*I(a)) - Cost(a) - Risk(a)

Informacja I(a) jest warunkowa względem uzyskania użytecznego wyniku; dlatego także mnożymy ją przez p_k. Uproszczenie zakłada, że niepowodzenie wykonania samo nie informuje o H i nie zależy od H. Pełny model powinien uwzględniać takie niepowodzenie jako dodatkowy wynik obserwacji.

Wartość, koszt i ryzyko są we wspólnej umownej skali użyteczności; lambda przelicza bity na tę skalę. Parametry nie są naturalnymi stałymi. Profile zabronione, przekraczające limit ryzyka, bez budżetu albo bez spełnionych zależności odpadają przed rankingiem. Wysoka liczba punktów nie może zalegalizować niedozwolonej akcji.

Wybieramy najwyższy dopuszczalny wynik, o ile przekracza min_score. W przeciwnym razie zwracamy stop_or_request_evidence. Remisy rozstrzyga identyfikator ASCII. To ranking heurystyczny o horyzoncie jednego kroku, nie dowód optymalności globalnej.

Bardziej decyzyjna alternatywa, gdy dostępny jest pełny model dalszych działań:

    VOI(a) = E_y[max_b E[V(b)|F,y]] - max_b E[V(b)|F] - Cost(a)

VOI premiuje informację, która może poprawić decyzję, a nie dowolny spadek entropii. VOI nie jest zaimplementowane w tym prototypie. Dla MVP należy ograniczyć hipotezy do istotnych dla celu, aby nie premiować bezcelowych eksperymentów.

## Przykład demonstracyjny

H1: utrata stanu aplikacji jest skutkiem błędu cache/persistencji. Prior 0.6. Test ma s=0.9, f=0.1.

    I(a) = 0.5124583014443723 bit
    P(H1 | +) = 0.9310344827586207
    P(H1 | -) = 0.14285714285714285

Przy lambda=0.8:

| Kandydat | P wykonania | G przed pomiarem | I | Koszt | Ryzyko | Wynik |
|---|---:|---:|---:|---:|---:|---:|
| Diagnostyka T1 | 0.9 | 0.1 | 0.5124583 | 0.12 | 0 | 0.338970 |
| Poprawka T2 | 0.8 | 0.9*0.6 | 0 | 0.25 | 0.08 | 0.102000 |
| Dokumentacja T3 | 0.95 | 0.2 | 0 | 0.08 | 0 | 0.110000 |

Przed pomiarem wygrywa T1. Po dodatniej obserwacji, wykorzystując ten sam profil poprawki:

    Score(T2) = 0.8 * 0.9 * (27/29) - 0.25 - 0.08 = 0.3403448275862069

T1 jest już zakończone, a T2 wyprzedza dokumentację. To przykład zmiany następnego kroku pod wpływem zarejestrowanego wyniku, nie dowód realnej skuteczności aplikacji ani LLM.

## Co należy zbadać na prawdziwych zadaniach

Porównaj tę samą pulę stanów i ten sam budżet LLM dla: prostego polecenia „wygeneruj następne zadanie”, rankingu bez składnika informacji oraz pełnego rankingu. Oddziel ocenę kandydatów od oceny ich wyboru; można utrzymywać ten sam zestaw kandydatów, by sprawdzić wyłącznie ranking.

Mierz odsetek zadań z trafnym uzasadnieniem w źródłach, odsetek osiągniętych kryteriów, postęp celu na jednostkę kosztu, duplikaty, błędnie uznane fakty, konieczne interwencje oraz błąd prognoz prawdopodobieństwa: średnią z (p_i-z_i)^2. Prognozy zapisuj przed wykonaniem. Ocena powinna używać nowszych lub odłożonych przypadków bez przecieku z przyszłości. Wyniki unit testów nie zastępują takiego eksperymentu.

## Python a TypeScript

Obie wersje wykonują ten sam rachunek bez bibliotek zewnętrznych i używają tego samego interfejsu Git. W badaniu nie wykazano przewagi jakości planów żadnego języka; nie wykonywano sesji generowania przez LLM.

Python rekomenduję jako domyślny język niewielkiego silnika eksperymentalnego: zwięzły zapis matematyki, dataclasses i prosty program CLI. TypeScript jest rozsądnym wyborem, gdy silnik ma być częścią istniejącego produktu TypeScript i współdzielić typy/protokoły. Jego statyczne unie i zawężanie typów pomagają modelować stany, ale samo type stripping w Node nie wykonuje sprawdzania typów. Ani adnotacje Pythona, ani deklaracje TypeScript nie zastępują walidacji danych z LLM.
