# Propozycje ulepszeń na podstawie benchmarku

```json
{
  "id": "benchmark-improvements-2026-09-10",
  "kind": "analysis",
  "version": 1,
  "date": "2026-09-10",
  "owner": "semcod/gitive",
  "status": "local-uncommitted",
  "source_revision": "9f6c7b1e9b8bc3475c7ec2e74a39b36039f5321a",
  "evidence": [
    "benchmark/runs/20260910T104959Z-48c133/summary.json",
    "benchmark/runs/20260910T104959Z-48c133/verification.json",
    "benchmark/runs/20260910T104959Z-48c133/iterations/gpt6--url_router--2.json",
    "benchmark/runs/20260910T104959Z-48c133/iterations/opus5--invoice_math--1.json"
  ]
}
```

## Ustalenia i zakres

Podstawą jest [końcowy przebieg live](../../benchmark/runs/20260910T104959Z-48c133/report.md), nie wcześniejszy pilot. Każde rozwiązanie wykonało trzy iteracje na każdym z trzech lokalnych projektów. Wszystkie ostatecznie osiągnęły 27/27 testów, bez zaobserwowanych regresji.

| Rozwiązanie | Etapy zakończone kompletem aktualnych testów | Zaakceptowane poprawki | Błędy wykonania iteracji | Wywołania LLM | Tokeny | Koszt SDK USD |
|---|---:|---:|---:|---:|---:|---:|
| glm53 | 9/9 | 5 | 0 | 10 | 11 628 | 0,026068 |
| gpt6 | 8/9 | 4 | 1 | 9 | 10 238 | 0,020033 |
| opus5 | 8/9 | 5 | 1 | 11 | 11 337 | 0,026734 |

Etapy obejmują także kroki bez zmian, gdy testy już przechodziły. Jedna poprawka może rozwiązać kilka etapów. Liczba commitów nie jest miarą jakości. Pojedynczy przebieg nie uzasadnia ogólnego rankingu szybkości ani kosztu.

[Adaptery benchmarku](../../benchmark/adapters.py) korzystają z rodzimych komponentów, ale dodają lokalne wykonanie i ocenę. Opus5 otrzymał dodatkowy wykonawca poprawek. Benchmark nie dowodzi działania pełnej produkcyjnej pętli GitHub żadnego projektu.

## glm53

### P1 — Rodzimy tryb naprawy projektu z nieprzechodzącymi testami

**Ustalenie z kodu:** `refactor_step` w [refactor.py](../../glm53/intuition/refactor.py) wymaga zielonych testów bazowych. Istniejący `repair_pr` dotyczy już utworzonego PR bota. Benchmark używa lokalnego wykonawcy, dlatego jego sukces nie dowodzi, że natywne wejście potrafi rozpocząć naprawę czerwonej gałęzi bazowej.

**Propozycja:** osobny tryb naprawy, który zapisuje błędy bazowe, wymaga poprawy wyniku i odrzuca nowe regresje. Zachować wymóg zielonej bazy dla zwykłej refaktoryzacji.

**Kryterium odbioru:** natywne CLI naprawia kontrolowany czerwony projekt; błędna poprawka zostaje wycofana; test działa bez `benchmark.adapters`.

### P1 — Rozdzielenie nagrody za wiedzę i za naprawę

**Ustalenie z kodu:** `persist` i `model.update` nagradzają nowe fakty. To odpowiada pierwotnemu modelowi przyrostu wiedzy, lecz nowy opis błędu nie oznacza skutecznej naprawy.

**Propozycja:** zapisywać osobno `knowledge_reward`, zmianę wyniku testów i akceptację poprawki. W trybie napraw aktualizować ocenę skuteczności na podstawie zweryfikowanego rezultatu wykonania.

**Kryterium odbioru:** kolejne nowe opisy nieudanej naprawy nie zwiększają estymaty jej skuteczności; historia zachowuje oba rodzaje nagrody.

### P2 — Telemetria i optymalizacja kontekstu

**Pomiar:** brak błędów; 11 628 tokenów i 10 wywołań. **Hipoteza:** selekcja trafniejszych fragmentów kodu i krótszych uzasadnień może obniżyć koszt. Sam pomiar nie wskazuje przyczyny różnic czasu.

**Propozycja:** rodzime raportowanie tokenów, kosztu, czasu, ponowień i `finish_reason` dla każdej fazy; wspólny budżet obejmujący ponowienia. Dopiero potem eksperyment z ograniczonym kontekstem.

**Kryterium odbioru:** ponowienia zużywają budżet; porównanie kilku powtórzeń pokazuje spadek tokenów bez utraty skuteczności.

## gpt6

### P0 — Kontrakt odpowiedzi i diagnostyka walidacji

**Pomiar:** `url_router`, iteracja 2, zakończyła się `Unexpected JSON fields` po jednym wywołaniu propozycji. Odpowiedź miała dwa tokeny wyjściowe i `finish_reason=stop`. Nie zapisano treści pozwalającej ustalić dokładne brakujące lub nadmiarowe pola.

**Ustalenie z kodu:** [util.fields](../../gpt6/intuition_github/util.py) używa identycznego komunikatu dla różnych naruszeń; klient wymusza obiekt JSON, co nie gwarantuje kontraktu zadania.

**Propozycja:** osobne schematy propozycji i poprawki, jednoznaczny przykład pustego wyniku z wymaganymi polami oraz diagnostyka typu, ścieżki, brakujących i nadmiarowych kluczy. Tryb `json_schema` stosować po potwierdzeniu wsparcia konkretnego endpointu; utrzymać walidację lokalną. [Dokumentacja LiteLLM](https://docs.litellm.ai/docs/completion/json_mode) rozróżnia JSON mode i obsługę schematów.

**Kryterium odbioru:** rozróżnienie pustej listy zadań, pustego obiektu, złego typu i nadmiarowych pól; brak osłabienia kontroli SHA i ścieżek.

### P1 — Odzyskiwanie po błędzie propozycji w granicach budżetu

**Ustalenie z kodu:** [controller.py](../../gpt6/intuition_github/controller.py) zapisuje niepowodzenia generowania poprawek, ale propozycja nie ma analogicznej obsługi błędu kontraktu.

**Propozycja:** zapisać stan nieudanej propozycji i umożliwić ograniczone ponowienie z konkretnym komunikatem walidatora. Przy limicie dwóch wywołań poprawiony plan może wymagać wykonania w następnym cyklu. Zużycie odpowiedzi należy rejestrować również wtedy, gdy parsowanie lub kontrola zakończenia odpowiedzi zgłasza wyjątek.

**Kryterium odbioru:** błędna propozycja nie przerywa trwałej pętli, restart zachowuje stan, a odzyskiwanie nie przekracza limitów wywołań i tokenów.

### P1 — Test całego kontrolera

**Ograniczenie dowodu:** benchmark korzysta z lokalnego wykonawcy oraz wyłącza cooldown zadań. Nie obejmuje pełnego cyklu pamięci, PR i ponownego wejścia kontrolera.

**Propozycja i kryterium odbioru:** test integracyjny rzeczywistego `Controller` z lokalnym zastępstwem transportu GitHub: nieudana propozycja → poprawka → nieudane testy → ponowienie → zaakceptowanie. Zweryfikować idempotencję, cooldown i wznowienie po restarcie.

## opus5

### P0 — Poprawienie parsera JSON

**Pomiar:** `invoice_math`, iteracja 1, zgłosiła `model did not return valid JSON`; późniejsza iteracja naprawiła projekt.

**Niezależnie odtworzony defekt:** `_first_json_array` w [llm.py](../../opus5/src/intuition/llm.py) liczy nawiasy wewnątrz napisów. Poprawne wejście `[{"title":"Handle literal ] in input"}]` zostaje ucięte i odrzucone. Brak pełnej odpowiedzi z benchmarku uniemożliwia przypisanie tamtego błędu właśnie temu defektowi.

**Propozycja:** najpierw zwykłe `json.loads`; przy usuwaniu otoczki używać dekodera JSON, który rozumie napisy i escape, zamiast liczenia nawiasów.

**Kryterium odbioru:** poprawne parsowanie nawiasów w napisach, cudzysłowów z escape, bloków kodu i checklist; jednoznaczne odrzucenie odpowiedzi uciętych i niezgodnych ze schematem.

### P1 — Własny wykonawca napraw

**Ograniczenie dowodu:** rodzime rozwiązanie proponuje i ocenia zadania. Poprawki kodu w benchmarku realizuje dodatkowy wykonawca.

**Propozycja:** przenieść wykonanie do modułu produktu: ograniczony zakres plików, walidacja poprawki, testy, rollback i zapis stanów zadania. Wynik testów powinien stanowić osobny sygnał uczenia; podjęcie zadania nie jest dowodem skutecznej naprawy.

**Kryterium odbioru:** trzy kontrolowane projekty naprawiane przez natywne CLI bez wykonawcy benchmarku; regresja odrzucona, wynik i aktualizacja modelu odtwarzalne z historii.

### P1 — Kontrola zakończenia odpowiedzi i timeoutów

**Ustalenie z kodu:** klient zwraca treść bez kontroli `finish_reason`; nie ma jawnej polityki timeoutów i ponowień porównywalnej z pozostałymi klientami.

**Propozycja:** rozróżnić uciętą odpowiedź, pustą treść, błędny JSON i błąd transportu. Dodać jawne limity czasu, ponowień oraz licznik zużycia także przy niepowodzeniu.

**Kryterium odbioru:** symulowany timeout i ucięty JSON kończą krok w określonym czasie, zapisują właściwą kategorię błędu i pozwalają wznowić pętlę bez podwójnego wykonania.

## Następny benchmark

1. Powtórzyć porównanie 5–10 razy, zmieniając kolejność rozwiązań; raportować mediany i rozrzut, osobno próby napraw i kroki bez zmian.
2. Rozdzielić jakość propozycji, wykonanie poprawki i pełny cykl kontrolera. Wyników adaptera nie utożsamiać z możliwościami natywnego produktu.
3. Zapisywać bezpieczną diagnostykę kontraktu i skrót odpowiedzi; pełne odpowiedzi potrzebne do odtworzenia błędu przechowywać prywatnie po usunięciu sekretów.
4. Dodać projekty wieloplikowe, celową regresję, nieaktualne SHA, restart procesu, timeout oraz wielokrotnie niepoprawny JSON.

## Kolejność i status

Najpierw parser Opus5 i kontrakt/diagnostyka GPT6, następnie natywny tryb naprawy czerwonej bazy GLM53 oraz wykonawca Opus5. Optymalizację kosztu poprzedzić powtarzanym pomiarem.

To lokalna analiza i propozycje. Nie zmieniono implementacji trzech rozwiązań ani nie uruchamiano nowych płatnych wywołań LLM podczas przygotowania rekomendacji.
