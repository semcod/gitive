# intuition

Konfiguracja LLM: wspólny `../.env` w workspace (`gitive/.env`),
`OPENROUTER_API_KEY`, `LLM_MODEL=openrouter/z-ai/glm-5.3` oraz
`LLM_REASONING_EFFORT=low`, przez LiteLLM.
Po przeniesieniu projektu osobno używany jest lokalny `.env`.

Task generation as **amortized inference** over facts that a repository already produces.
Git history, GitHub Actions logs and in-code markers go in; scored, ranked GitHub issues
come out; closing those issues teaches the ranker. No database, no vector store, no
service — the repo itself is the state.

```
git log ─┐
gh run  ─┼─► facts.jsonl ─► s_t (state) ─┐
grep    ─┘                  r_t (friction)┼─► δ_t ─► LLM candidates ─► U(c) ─► gh issue create
                            g   (goal)  ──┘                             │
                                    weights.json ◄── SGD ◄── issue closed
```

## Quickstart

```bash
pip install -e .
cp .env.example .env         # add OPENROUTER_API_KEY
intuition init
intuition cycle --dry-run    # score and print, create nothing
intuition cycle              # open the top-ranked issues
intuition explain            # why those, feature by feature
```

Then commit `.github/workflows/intuition-loop.yml` and set two repository secrets:
`OPENROUTER_API_KEY`, and optionally `INTUITION_PAT`.

## Commands

| command | what it does |
|---|---|
| `intuition init` | scaffold `.intuition/`, write `.env.example`, create the `intuition` label |
| `intuition ingest` | pull new facts from git, Actions and code markers |
| `intuition cycle` | one loop turn: observe → tension → propose → score → open issues |
| `intuition feedback` | label past proposals from issue state, one SGD step each |
| `intuition status` | tension history, learned weights, hit rate |
| `intuition explain` | per-feature breakdown of recent scores |

## How the loop closes

Three triggers, deliberately overlapping:

* **`schedule`** — a 6-hour heartbeat. This alone keeps the loop running forever.
* **`workflow_run: completed`** — a finished CI run is new evidence, so the loop reacts to
  a red pipeline within minutes instead of hours.
* **`issues: closed`** — the reward signal. `theta` updates the moment a human acts.

Commits and issues created with `GITHUB_TOKEN` do **not** trigger further workflow runs.
That GitHub behaviour is what stops "infinite" from meaning "runaway". Set `INTUITION_PAT`
only if you want issue events to cascade, and lower `INTUITION_MAX_OPEN` if you do.

## Safety rails

These exist because an unattended issue generator is a spam machine by default.

| rail | mechanism |
|---|---|
| WIP limit | never more than `INTUITION_MAX_OPEN` open generated issues; the cycle exits early |
| throughput | at most `INTUITION_PER_CYCLE` issues per turn |
| relevance gate | `surprise` scores zero unless the candidate clears `align_floor` against δ |
| redundancy | cosine against every past proposal, weighted by a negative θ |
| grounding | the prompt forbids tasks not traceable to a supplied fact |
| honest history | `facts.jsonl` and `ledger.jsonl` are append-only; corrections are new rows |
| kill switch | `INTUITION_DRY_RUN=true` scores everything and creates nothing |

## Configuration

Everything is env-driven; see `.env.example`. The knobs that actually change behaviour:

| variable | default | effect |
|---|---|---|
| `INTUITION_TAU` | `0.7` | softmax temperature. Low = finish one thread; high = scattered |
| `INTUITION_HALF_LIFE_DAYS` | `14` | how fast the past stops counting |
| `INTUITION_FRICTION_WEIGHT` | `1.0` | how hard CI failures pull attention away from the roadmap |
| `INTUITION_ALIGN_FLOOR` | `0.30` | raise it if proposals drift off-project |
| `INTUITION_LR` | `0.05` | learning rate; raise for fast repos, lower for noisy teams |

## Embeddings, honestly

OpenRouter routes chat completions, not embeddings. Rather than pretend otherwise, the
package ships a deterministic **hashing embedder** (signed feature hashing over word
tokens and character 4-grams) used whenever `INTUITION_EMBED_MODEL` is empty or the
provider fails. It is lexical, not semantic — good enough for redundancy detection and
for the decay-weighted centroids, weaker at recognising that "retry budget" and
"exponential backoff" are the same subject. Point `INTUITION_EMBED_MODEL` at a real
provider (`openai/text-embedding-3-small`, or a local `ollama/nomic-embed-text`) and
ranking quality goes up immediately. Nothing else changes.

## Layout

```
.intuition/
  facts.jsonl     append-only observations {id, ts, kind, ref, text}
  goal.json       g, regenerated when the tension converges
  weights.json    theta + tension history
  ledger.jsonl    every proposal, its features, its outcome
src/intuition/
  model.py        the maths — ~120 lines, no framework
  facts.py        git + gh run ingestion, CI log compression
  embed.py        litellm embeddings with offline fallback
  llm.py          litellm/OpenRouter completion, strict JSON
  core.py         cycle() and feedback()
  gh.py           gh CLI adapter
```

See [`docs/model.md`](docs/model.md) for the derivation.

## Tests

```bash
pip install -e ".[dev]" && pytest -q      # normal
python3 tools/offline_test_runner.py      # air-gapped, no pytest needed
```

The suite runs the entire cycle offline with a stubbed LLM: no network, no `gh`, no keys.

## License

Apache-2.0

### Lokalne wykonanie zadania

`intuition repair --repo-root /projekt --task-id ID_Z_LEDGERU --test '["python3","-B","-m","unittest","discover","-s","tests"]'`

`INTUITION_ROOT` wskazuje lokalny ledger zawierający zadanie z polami `files` i
`phi`. Repozytorium musi mieć czysty checkout i skonfigurowaną tożsamość Git.
Wykonawca pracuje w klonie; przyjmuje wyłącznie poprawkę przechodzącą cały zestaw
testów. Odrzucony kod jest wycofywany. Wyniki i oddzielne wagi wykonania trafiają
do `.intuition-repair/` w Git. Zielona baza nie wywołuje ponownie LLM.
Nie powstają zdalne issues ani PR. Komenda testowa musi być zaufana; usunięcie
kluczy ze środowiska testów nie jest izolacją systemową.
`LLM_TIMEOUT_SECONDS` ogranicza czas zapytania (domyślnie 120); automatyczne
ponowienia SDK są wyłączone.
