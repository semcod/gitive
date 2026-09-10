# Bezpieczeństwo i granice zaufania

## Zasada

LLM tworzy dane propozycji, nie polecenia i nie uprawnienia. Log, issue, komentarz, nazwa pliku ani tekst źródła nie mogą rozszerzyć allowlisty, zmienić workflowu, wyłączyć testu lub ustanowić wyniku sukcesu.

Zaufane są: operator, wybrana wersja gałęzi domyślnej, kod kontrolera, jego konfiguracja, stały zestaw testów, używane zależności i mechanizmy uwierzytelnienia GitHub. Kontrola jest inżynierska, nie formalnie udowodniona.

## Oddzielenie procesów

Job kontrolera odczytuje źródła jako bajty przez Git Data API. Nie robi checkoutu kandydata, nie importuje go, nie uruchamia kodu modelu ani komend z issue. Weryfikator najpierw sprawdza PR/repo/gałąź/SHA/kompletną listę zmienionych plików. Następny job pobiera niezmienny SHA, uruchamia stały launcher, przekazuje procesom testów ograniczone środowisko bez `GH_TOKEN`, `OPENROUTER_API_KEY`, `GITHUB_ENV` i `GITHUB_OUTPUT`. Osobny job raportera pobiera wyłącznie zaufany kontroler; ponownie sprawdza PR przed opublikowaniem statusu.

`persist-credentials: false` jest ustawione przy każdym checkout. Actions przypięto do pełnych SHA, a Dependabot proponuje ich aktualizacje. Nie użyto `pull_request_target` ani cache współdzielonego z nieufnym kandydatem. Przypięcie do SHA ogranicza ruchome zależności, ale nie dowodzi bezpieczeństwa samej akcji.

**To nie jest pełny sandbox z kontrolą sieci i systemu operacyjnego.** Runner Actions ma własne tokeny infrastrukturalne i mechanizmy komunikacji; czyste środowisko procesu nie stanowi bariery jądra. Kod testów może korzystać z sieci, uszkodzić własny job albo ujawnić źródła dostępne w tym jobie. Nie używaj trwałego self-hosted runnera z poświadczeniami lub montowaniami produkcyjnymi. Dla nieufnych repozytoriów potrzebna jest silniejsza izolacja i kontrola wyjścia sieciowego.

## Sekrety i prywatność

Lokalny `.env` nie trafia do Git ani wydań. Paczka startowa ma tylko puste wartości kluczy. Sekrety Actions są wstrzykiwane do określonego kroku, nie do joba wykonującego kandydata. Nie należy przechowywać w `.env` kluczy, których kontroler nie potrzebuje.

Redaktor maskuje znane wartości sekretów ze środowiska, typowe tokeny GitHub/OpenRouter, nagłówki uwierzytelnienia, klucze prywatne, poświadczenia w URL oraz sekwencje sterujące. **Maskowanie jest niepełne**: nie rozpoznaje arbitralnych danych osobowych, nietypowych sekretów, kodowania, fragmentacji i wszystkich form credentiali. Surowe logi pozostają na GitHub zgodnie z jego retencją; oczyszczone fragmenty są trwale wersjonowane w repozytorium i przesyłane do OpenRouter/dostawcy wybranego modelu. Prywatne repozytorium nie oznacza, że danych nie widzi dostawca LLM. Przed włączeniem sprawdź zasady organizacji i dostawcy.

Podejrzenie sekretu w pliku docelowym powoduje jego pominięcie lub przerwanie poprawki; nie zmieniamy po cichu kodu przez redakcję. Nie logujemy pełnych promptów/odpowiedzi SDK ani tekstu wyjątku dostawcy. Tytuły i opisy modelu mają neutralizowane znaczniki sterujące issue i wzmianki `@`, ale nie traktuj ich jako zaufanej dokumentacji.

## Prompt injection i błędna ocena

Komunikat systemowy oddziela logi od instrukcji, lecz sam prompt nie jest zabezpieczeniem. Istotne ograniczenia wykonuje Python: ścisły JSON, identyfikatory faktów, dozwolone profile, hash starego pliku, maksymalny diff, niezmienny SHA i brak narzędzi powłoki. Model wciąż może zaproponować merytorycznie złą lub złośliwą zmianę w dozwolonym pliku. Dlatego domyślnie nie ma automatycznego scalania.

Testy są niezmienne dla agenta, ale nie dowodzą pełnej poprawności, braku podatności ani spełnienia wszystkich kryteriów tekstowych. Zmiana może przejść testy i nadal być niepożądana. Beta aktualizuje prawdopodobieństwo wyniku pipeline'u; to nie certyfikat jakości. Domyślny przyrost informacji z dowolnych logów to zero, nie zmyślony rozkład diagnostyczny.

## Zależności

`requirements.txt` przypina LiteLLM i python-dotenv. Nie zawiera kompletnego, zweryfikowanego w tym środowisku lockfile zależności przechodnich z hashami. Instalacja odbywa się przed krokiem udostępniającym klucze, ale złośliwy pakiet może utrwalić zmiany w środowisku i przechwycić sekret w późniejszym kroku. Ta kolejność nie usuwa ryzyka supply chain. Przed produkcją zbuduj i przejrzyj hash-pinned lockfile albo zaufany obraz z zależnościami. Nie deklarujemy zdalnego audytu ani braku podatności tych wersji.

## Operacje Git i odzyskiwanie

Zapisy gałęzi nie używają force. Wstępne sprawdzenie refa i fast-forward wykrywają konkurencyjne zapisy; nie są rozproszoną transakcją obejmującą Git, issues i API LLM. Niektóre błędy mogą zostawić osierocony nieosiągalny commit lub jednorazowo powielone uruchomienie CI. Przygotowany SHA zapisany w pamięci, stabilny marker issue i deterministyczna gałąź pozwalają wznowić większość przerwanych operacji bez kolejnego płatnego wygenerowania poprawki. Nie obiecujemy uniwersalnej semantyki exactly-once.

Budżet opiera się na historii dedykowanej gałęzi. Osoba mogąca ją usunąć lub przepisać może zresetować także budżet. Ogranicz możliwość usuwania/force-push pamięci, wykonuj kopie i ustaw niezależny limit u dostawcy. Autoryzowany człowiek mogący zmienić główny kontroler także może zmienić reguły — to jawna granica zaufania.

## Reakcja na incydent

Wyłącz `INTUITION_ENABLED` i `INTUITION_CD_ENABLED`, anuluj aktywne joby, zablokuj i obróć klucze w razie wycieku, sprawdź logi/commity/PR-y i usuń automatyczne scalanie. Samo wyłączenie cron nie anuluje uruchomionych procesów ani wcześniej zleconego auto-merge. Nie publikuj podejrzanych logów w publicznych issues.
