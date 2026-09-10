# Dokumentacja gitive

- [Odbiór shellu kontekstowego](analysis/context-shell-2026-09-10.md) — 74 testy i wdrożenie lokalne.
- [Shell projektu i ticketu](information/context-shell.md) — kontekst, operacje wykonawców i synchronizacja GitHub.

- [DigitalTwin P0 — wykonanie i testy kontenera](analysis/digitaltwin-p0-2026-09-10.md).

- [Planfile, doctor-agent i import PC do noVNC](analysis/planfile-doctor-agent-2026-09-10.md) — rzeczywista synchronizacja ticketów, profile i testy.

- [Architektura DigitalTwin, workspace, projektów i ticketów](information/workspace-project-architecture.md) — podział odpowiedzialności, struktury i cykl realizacji.
- [Plan DigitalTwin, aplikacji GUI i delivery](refactoring/workspace-delivery.md) — etapy implementacji, migracja i odbiór.

- [Dockerowa pętla benchmark / Codex](information/benchmark-codex-loop.md) — panel, noVNC, uruchomienie i status integracji.

- [Poprawki jakości i benchmark v2](analysis/quality-fixes-v2-2026-09-10.md) — ochrona API, retry uciętych odpowiedzi, diagnostyka GPT6 i natywny repair Opus5 w benchmarku.

- [Zapisy wejścia i wyjścia LLM](information/benchmark-transcripts.md) — zakres, prywatne pliki i weryfikacja SHA-256.

- [Ponowny benchmark i autonomiczne wydawanie](analysis/autonomous-delivery-2026-09-10.md) — wyniki live, audyt GitHub, poprawki P0 weryfikacji/wydania i pozostałe braki Issue → PR → merge → release.

- [Wdrożenie poprawek po benchmarku](analysis/benchmark-fixes-2026-09-10.md) — zmiany, użycie i wyniki weryfikacji.

- [Ulepszenia po benchmarku — 2026-09-10](analysis/benchmark-improvements-2026-09-10.md) — priorytety dla GLM53, GPT6 i Opus5, dowody i kryteria odbioru.

- [Benchmark trzech pętli napraw](information/repair-benchmark.md) — metodologia i timestampowane raporty w `benchmark/`.

- [Testy rzeczywiste LLM i GitHub — 2026-09-10](analysis/live-project-tests-2026-09-10.md) — wyniki trzech projektów i poprawki konfiguracji.

- [gitive-overview](information/gitive-overview.md) — cel repozytorium, zakres trzech wariantów i sposób weryfikacji.
- [GLM53](../glm53/docs/README.md) — instrukcja lokalnego wariantu GLM-5.3.
- [GPT-6](../gpt6/README.md) — dokumentacja kontrolera GitHub-native i jego architektury.
- [Opus 5](../opus5/README.md) — opis pakietu `intuition` i modelu rankingu.

Status: dokumentacja lokalna, wersjonowana i publikowana wraz z kodem w `main`.

- [20260910T104156Z-4580a6 — mock](../benchmark/runs/20260910T104156Z-4580a6/report.md)
- [20260910T104535Z-b48f5a — pilot](../benchmark/runs/20260910T104535Z-b48f5a/report.md)
- [20260910T104959Z-48c133 — live](../benchmark/runs/20260910T104959Z-48c133/report.md)

- [20260910T115313Z-3df9cb — ponowny benchmark live](../benchmark/runs/20260910T115313Z-3df9cb/report.md)

- [Jakość odpowiedzi na podstawie pełnych zapisów](analysis/llm-transcript-quality-2026-09-10.md) — 33 wywołania, konkretne błędy propozycji i dodatkowe testy.
- [20260910T120448Z-4012c1 — live z pełnym zapisem SDK](../benchmark/runs/20260910T120448Z-4012c1/report.md)
