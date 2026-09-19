---
{
  "schema": "wellmanifest.docs/document/v1",
  "id": "pr-stack-integration",
  "kind": "analysis",
  "version": 1,
  "title": "Integracja stosu PR Gitive",
  "status": "implemented",
  "owner": "semcod/gitive",
  "created": "2026-09-10",
  "updated": "2026-09-10",
  "review_after": "2026-09-17",
  "source_revision": "f11518652b51e7f7edaaa5c38c9348e5417e3cf0",
  "affected_repositories": [
    "semcod/gitive"
  ],
  "evidence": [
    "https://github.com/semcod/gitive/pull/2",
    "https://github.com/semcod/gitive/pull/4",
    "https://github.com/semcod/gitive/pull/6",
    "https://github.com/semcod/gitive/pull/8"
  ]
}
---

# Integracja stosu PR Gitive

<!-- docs:section question -->
## Pytanie

Czy PR-y #2, #4, #6 i #8 można zintegrować z aktualnym main bez utraty istniejącej implementacji i z niezależną walidacją?

<!-- docs:section scope -->
## Zakres

Właścicielem jest semcod/gitive. Analiza dotyczy istniejących gałęzi ticket/001, ticket/003, ticket/005 i ticket/007. Nie obejmuje zmiany chronionej polityki Validatora ani wdrożenia produkcyjnego. Kanoniczny [plan produktu](../refactoring/workspace-delivery.md) pozostaje osobnym dokumentem.

<!-- docs:section method -->
## Metoda

Odczyt GitHub i konfiguracji lokalnej, porównanie drzew i historii, uzgodnienie bieżącego main commitami merge na gałęziach PR bez force-push. Prywatne kopie rekordów worktree zachowano przed ich ponownym wygenerowaniem przez opublikowany planner v5. Każdy nowy rekord przeszedł walidację filesystem. Brudny główny checkout pozostawiono bez zmian.

<!-- docs:section evidence -->
## Dowody

Bazą odczytu jest `d9eb3b44c0ef866ae6496bf95b7819c25788193a`. Ten commit zawiera implementację DigitalTwin i shellu, choć nie jest potomkiem wcześniejszych gałęzi PR.

- #2: po rozwiązaniu siedmiu konfliktów pozostało pięć dodatkowych plików względem main: wheel Planfile, jego manifest oraz trzy workflow pod gpt6/.github/workflows. Nie są to rootowe workflow GitHub tego repozytorium.
- #4: po uzgodnieniu drzewo jest identyczne z #2; implementacja shellu jest już w main. Nie ma osobnej zmiany produktu do scalenia z #2.
- #6: pozostaje implementacja terminala projektu, 16 plików względem uzgodnionego shellu.
- #8: pozostaje centrum WWW, 24 pliki względem terminala przed dodaniem tego raportu.

<!-- docs:section facts -->
## Fakty

Chroniony adapter Validatora zwrócił `direct_pr_registry_target_unknown:semcod/gitive`. OneDev zwrócił `unknown repositories: semcod/gitive`. Nie zaobserwowano przypisanego profilu PR w konfiguracji koordynatora. Brak profilu nie oznacza awarii całej lokalnej infrastruktury CI.

Lokalne testy używają izolowanego Pythona 3.13, Node 22.23.1, zależności benchmark/requirements.txt i pakietu Planfile dołączonego do PR. Początkowe próby ujawniły braki środowiska: starszy Node, NumPy, LiteLLM, age i llm-accounts. Po uzupełnieniu zależności wszystkie cele make test przeszły na trzech różnych drzewach. Testy aplikacji: #2 — 74, #6 — 79, #8 — 86, bez pominięć. Shell #4 ma identyczne drzewo jak #2. Wspólne zestawy: GLM53 28, GPT6 Python 25, TypeScript 25, integracje GitHub 87, Opus5 14+3+3, benchmark 11; crosscheck również zakończył się sukcesem. Wheel i sdist #8 zbudowano. Oba vendored wheels sprawdzono względem hashy manifestów.

<!-- docs:section hypotheses -->
## Hipotezy

Rozbieżna historia najprawdopodobniej wynika z oddzielnego skopiowania części zmian na main. Równoważność drzew jest sprawdzona; sposób wcześniejszej publikacji nie jest tu rozstrzygany.

<!-- docs:section limitations -->
## Ograniczenia

Lokalny sukces testów nie jest niezależnym zatwierdzeniem. Autor tego raportu nie uruchamiał self-approval ani merge. Równoległa publikacja przez konto tom-sapletta-com scaliła #2 o 19:56:24Z, #4 o 19:57:05Z, #6 o 19:57:18Z i #8 o 19:57:30Z dnia 2026-09-10. GitHub nie zwrócił reviews ani checks dla tych PR-ów. Nie potwierdzono więc chronionej niezależnej ścieżki publikacji. Końcowy main to f11518652b51e7f7edaaa5c38c9348e5417e3cf0; git diff potwierdza identyczność z testowanym b840c2c422185b3b1334b7537a0ef331b93ed06e. Odbiór Docker/noVNC i przeglądarki z wcześniejszych raportów nie został ponowiony w tej integracji.

<!-- docs:section recommendations -->
## Dalsza publikacja

Wymagany jest niezależnie przyjęty i wdrożony profil OneDev oraz profil publikacji Validatora dla semcod/gitive. Profil powinien zachować wszystkie cele make test, Node 22, zależności testowe i sprawdzenie rzeczywistego połączenia aktualnego head z aktualną bazą. Wszystkie cztery PR-y są już merged, więc nie należy ponownie ich scalać. Przed kolejną publikacją trzeba uzyskać chronione wyniki dla bieżącego head/base. Brak profilu nie uprawnia autora zmian do zastąpienia niezależnego aktora.

Nowy raport jest lokalny w worktree ticket-007; nie był częścią scalonego PR #8. Checker z niezmiennej rewizji ebe7501063ef4f3e63ded610c2d3183010ca636e sprawdził raport wraz z indeksem i lokalnym przypięciem .governance/docs.json. Nie dowodzi to wdrożenia bramy w CI ani migracji historycznej dokumentacji.

## Odbiór końcowego main

Pełne `make test` na czystym eksporcie commita `f11518652b51e7f7edaaa5c38c9348e5417e3cf0` zakończyło się kodem 0. Przeszły wszystkie zestawy, w tym 86 testów aplikacji bez pominięć. Prywatny receipt `receipt:gitive-pr-integration/published-tests` ma SHA-256 `48096a0ec4b2bcd8c9d3f6ea5287e34a55d35b46a5c3e2564e6c8589785eb949`. To odbiór lokalny po scaleniu, nie niezależne zatwierdzenie PR.
