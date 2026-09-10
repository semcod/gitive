# Źródła i zakres weryfikacji

Dokumentacja pierwotna sprawdzona 10 września 2026. Odnośniki dotyczą zachowania narzędzi, nie dowodzą wykonania projektu na zdalnym koncie. Własne formuły priorytetu, konfiguracja limitów i topologia projektu są decyzjami implementacyjnymi.

- **S1 — LiteLLM/OpenRouter:** https://docs.litellm.ai/docs/providers/openrouter — prefiks modelu, klucz API, endpoint, nagłówki aplikacji.
- **S2 — GitHub: wyzwalanie workflowów:** https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow — ograniczenia GITHUB_TOKEN, wyjątki dispatch, zatwierdzanie workflowów PR utworzonych przez automatyzację.
- **S3 — GitHub: zdarzenia Actions:** https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows — workflow_run, granice zaufania, harmonogram, gałąź domyślna, ograniczenia długości łańcuchów i nieaktywność publicznych repozytoriów.
- **S4 — GitHub CLI:** https://cli.github.com/manual/gh_run_view ; https://cli.github.com/manual/gh_issue_create ; https://cli.github.com/manual/gh_pr_create ; https://cli.github.com/manual/gh_workflow_run — logi, issues, PR i jawne uruchamianie workflowów.
- **S5 — GitHub Git Data API:** https://docs.github.com/en/rest/git/refs?apiVersion=2022-11-28 ; https://docs.github.com/en/rest/git/commits?apiVersion=2022-11-28 ; https://docs.github.com/en/rest/git/trees?apiVersion=2022-11-28 — refy, brak force, obiekty commit/tree/blob.
- **S6 — Opublikowane zależności:** https://pypi.org/project/litellm/1.100.1/ ; https://pypi.org/project/python-dotenv/1.2.2/ — przypięte bezpośrednie wersje. Nie stwierdzono testem lokalnym instalowalności całego zestawu zależności przechodnich; patrz raport.
- **S7 — OpenRouter: klucze i limity:** https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key — limit klucza i użycie; twardy limit kredytowy jest osobną warstwą od lokalnego licznika wywołań.
- **S8 — GitHub CLI merge:** https://cli.github.com/manual/gh_pr_merge — auto-merge i dopasowanie do SHA; dokumentacja ochrony: https://docs.github.com/en/rest/branches/branch-protection?apiVersion=2022-11-28 .

## Przypięcia oficjalnych akcji

Weryfikowano oficjalne commity dla wskazanych wydań; nie są przedstawiane jako zawsze najnowsze wersje. Dependabot proponuje aktualizacje, które powinny przejść przegląd.

| Akcja | Wydanie | SHA |
|---|---|---|
| actions/checkout | v5.0.0 | `08c6903cd8c0fde910a37f88322edcfb5dd907a8` |
| actions/setup-python | v6.0.0 | `e797f83bcb11b83ae66e0230d6156d7c80228e7c` |
| actions/setup-node | v5.0.0 | `a0853c24544627f65ddf259abe73b1d18a591444` |
| actions/upload-artifact | v5.0.0 | `330a01c490aca151604b8cf639adc76d48f6c5d4` |
| actions/download-artifact | v5.0.0 | `634f93cb2916e3fdff6788551b99b062d0335ce0` |

Źródłem są strony `https://github.com/actions/NAZWA/releases/tag/WERSJA` i odpowiadające im strony commitów. Hosted runner `ubuntu-24.04` jest konfiguracją docelową; własny runner musi spełniać wymagania Node/runner wskazane w opisach akcji.
