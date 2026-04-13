# Progress Checklist

Checklist nay duoc dung de track tien do roadmap o muc implementation + benchmark.

## Phase 0

- [x] Co starter benchmark suite trong `docs/evals/context-engine-starter.json`
- [x] Co regression assertions cho suite va case
- [x] Co baseline snapshot va baseline compare
- [x] Co `docs/roadmap/capability-matrix.md`
- [ ] Mo rong benchmark sang 2-3 codebase mau ngoai repo hien tai

## Navigation

- [x] Query theo symbol/module/file
- [x] Module path / hotspots / bridges
- [x] Entrypoint discovery
- [ ] `references`/`definitions` on dinh cho nhieu language hon
- [x] Hierarchy query day du cho package/module/class/function

## Intent

- [x] `explain <symbol>`
- [x] `context-for <task>` voi `bugfix/feature/refactor/onboarding`
- [x] Summary-first bundle gom code/tests/docs
- [x] Summary generation co he thong o file/class/function
- [x] Typed semantic edges cho code

## Dependency + Flow

- [x] `callers`, `callees`, `imported-by`
- [x] `module-deps`, `module-path`, `flow`, `why-related`
- [x] Task-aware path/ranking cho `query_graph.py` / `module_graph.py`
- [ ] Runtime/data-flow analyzer that su
- [ ] Cross-file resolution sau hon cho aliasing/dynamic dispatch

## Impact

- [x] `impact <symbol>`
- [x] `files-for-change <task>`
- [x] `verify-after-change <task>`
- [x] `untested-impact <symbol>`
- [x] Public API boundary scoring rieng
- [x] Graph diff truoc/sau thay doi

## Internal Docs

- [x] Document extraction + cross-reference
- [x] Typed doc classification (`readme/spec/design/domain/adr/runbook/incident/api_contract`)
- [x] `docs-for --mode/--type`
- [x] Typed docs duoc dua vao context assembly va impact display
- [x] Doc-code drift detection (`doc-drift`)
- [x] Semantic extraction cho workflow/constraints/decisions

## Evals And Ops

- [x] `system-wiki eval`
- [x] `--write-baseline`
- [x] `--compare-baseline`
- [x] `--update-baseline-if-better`
- [x] Baseline delta reporting trong output
- [ ] CI wiring cho baseline/eval gate
- [ ] Do `time to first useful edit`

## Manual Check Commands

```bash
system-wiki eval
system-wiki eval --compare-baseline docs/evals/baseline.json
system-wiki query context-for --mode feature "task-aware path ranking and context assembly in query_graph and module_graph"
system-wiki query docs-for --mode onboarding --type readme main
system-wiki query semantics query_graph.py
system-wiki query graph-diff wiki-out/graph-before.json
system-wiki query verify-after-change --mode feature "task-aware path ranking and context assembly in query_graph and module_graph"
system-wiki query untested-impact query_graph.py
```
