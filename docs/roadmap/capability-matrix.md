# Capability Matrix

Tai lieu nay chot "done" theo 4 cau hoi lon trong `CODEBASE_UNDERSTANDING_PLAN.md` va ghi lai maturity hien tai.

## Navigation

| Capability | Current | Notes |
| --- | --- | --- |
| Search symbol/module/file | Partial | `search`, `definitions`, `file`, `symbols`, `modules`, `module` da dung duoc |
| Qualified symbol identity | Partial | co `qualified_name` cho nhieu node, nhung chua co `references`/`definitions` that su on dinh cho moi language |
| Module path and topology | Good | `module-deps`, `module-path`, `module-hotspots`, `module-bridges` |
| Entrypoint-aware navigation | Good | `entrypoints`, `entrypoints-for`, `flow` |

## Intent

| Capability | Current | Notes |
| --- | --- | --- |
| Explain symbol | Good | `explain` + summary metadata da co, summary heuristic da phu module/class/function/method |
| Summary-first task context | Good | `context-for` da group focus/files/tests/docs theo mode |
| Typed semantic edges | Good | da co heuristic semantic edges `validates`, `persists`, `orchestrates` va surfacing qua summary metadata |
| File/class/function summaries | Good | summary heuristic da tong hop tu container, methods, calls, dependencies, callers, va signatures |

## Dependency And Flow

| Capability | Current | Notes |
| --- | --- | --- |
| Call/import queries | Good | `callers`, `callees`, `imported-by`, `why-related` |
| Module dependency graph | Good | `module_graph.py` va query surface da on dinh |
| Task-aware path/ranking | Good | context assembly + entrypoint ranking da co benchmark |
| Runtime/data-flow reasoning | Partial | flow hien la structural/query-time, chua phai runtime analyzer |

## Impact

| Capability | Current | Notes |
| --- | --- | --- |
| Direct blast radius | Good | `impact <symbol>` co callers/importers/docs/tests/risk |
| Change planning | Good | `files-for-change`, `verify-after-change` |
| Untested impact | Partial | `untested-impact` da co file/module heuristics, chua co test mapping chac chan |
| Public API boundary risk | Good | `impact`, `files-for-change`, `verify-after-change` da co heuristic boundary scoring rieng cho symbol public-facing |
| Graph diff before/after | Good | `graph-diff <before> [after]` so sanh node/edge/module/file delta giua 2 snapshots |

## Internal Docs

| Capability | Current | Notes |
| --- | --- | --- |
| Doc extraction | Good | headings/definitions/links/cross-doc concepts da co |
| Typed doc classification | Good | `readme`, `spec`, `design`, `domain`, `adr`, `runbook`, `incident`, `api_contract` |
| Docs-aware retrieval | Good | `docs-for --mode/--type`, typed doc boosts trong `context-for` |
| Drift detection | Partial | `doc-drift` da co query-time heuristic cho stale/missing/weak docs, chua co full-repo audit hay semantic drift |
| Semantic doc extraction | Good | doc hub node da trich `workflow_signals`, `constraint_signals`, `decision_signals` va dua vao summary |

## Evals

| Capability | Current | Notes |
| --- | --- | --- |
| Repeatable retrieval eval | Good | `system-wiki eval` + suite assertions |
| Baseline compare | Good | `--compare-baseline` + delta reporting |
| Baseline maintenance | Partial | `--update-baseline-if-better` da co, chua co CI wiring |
| Time-to-edit metrics | Not started | chua do duoc `time to first useful edit` |
