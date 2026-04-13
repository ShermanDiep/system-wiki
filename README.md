# system-wiki

`system-wiki` la mot fork scaffold tu pipeline graph hien co, duoc dat lai huong toi mot muc tieu lon hon:

- hieu codebase
- hieu docs noi bo
- giam token spend cho viec tim va hieu code
- tro thanh mot context engine cho coding agents

Project moi nay giu nen tang:

- structural extraction bang tree-sitter
- document extraction
- graph build + clustering + query
- write-back vao `wiki-out/`

Ngon ngu code da duoc nang cap tiep cho use case mobile:

- Swift
- Kotlin
- Java
- Objective-C (`.m`, `.mm`, va Objective-C headers `.h` duoc nhan dien theo heuristic)

Va duoc dinh huong de mo rong theo roadmap trong [CODEBASE_UNDERSTANDING_PLAN.md](./CODEBASE_UNDERSTANDING_PLAN.md):

- navigation tot hon
- intent summaries cho code
- dependency + flow analysis
- impact analysis / blast radius
- support cho spec, design docs, domain docs
- task-aware context assembly de giam token

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
system-wiki .
```

Smoke test:

```bash
scripts/smoke-test.sh .
```

New here?

- Start with [docs/onboarding/first-30-minutes.md](/Users/diephung/Downloads/my-llm-wiki-main/system-wiki/docs/onboarding/first-30-minutes.md)

## CLI

```bash
system-wiki .                      # build graph
system-wiki query stats           # summary
system-wiki query search <term>   # search nodes
system-wiki query entrypoints     # likely entrypoints/orchestrators
system-wiki query entrypoints-for extract_public_api
system-wiki query flow --depth 4 main
system-wiki query why-related system_wiki/__main__.py system_wiki/extract_python_postprocess.py
system-wiki query module <path>   # inspect one module and its deps
system-wiki query module-path A B # shortest path between modules
system-wiki query module-hotspots # rank heavily connected modules
system-wiki query module-bridges  # rank bridge modules
system-wiki query docs-for --mode onboarding --type readme main
system-wiki query doc-drift --mode feature query_graph.py
system-wiki query untested-impact <symbol>
system-wiki query verify-after-change --mode bugfix "<task>"
system-wiki eval                  # run starter benchmarks, fail on regression
system-wiki eval --write-baseline docs/evals/baseline.json
system-wiki eval --compare-baseline docs/evals/baseline.json
system-wiki eval --update-baseline-if-better docs/evals/baseline.json
system-wiki lint                  # health check
system-wiki watch .               # rebuild on changes
system-wiki note "<insight>"      # write back insight
```

## Package Layout

```text
system-wiki/
  system_wiki/                    # core package
  docs/onboarding/                # practical reading path for new developers
  docs/roadmap/                   # capability matrix + progress checklist
  scripts/
  CODEBASE_UNDERSTANDING_PLAN.md  # roadmap for the new direction
```

## Scope Of This Fork

Day la project moi duoc tao de tiep tuc phat trien theo plan trong repo hien tai, voi branding va metadata rieng cho `system-wiki`.
