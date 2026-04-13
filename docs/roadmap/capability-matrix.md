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
| Explain symbol | Partial | `explain` + summary metadata da co, nhung summary generation chua day du o moi file |
| Summary-first task context | Good | `context-for` da group focus/files/tests/docs theo mode |
| Typed semantic edges | Not started | chua co `validates`, `persists`, `orchestrates`, ... |
| File/class/function summaries | Partial | dua nhieu vao metadata/existing comments |

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
| Public API boundary risk | Partial | dua nhieu vao dependency graph, chua co boundary model rieng |

## Internal Docs

| Capability | Current | Notes |
| --- | --- | --- |
| Doc extraction | Good | headings/definitions/links/cross-doc concepts da co |
| Typed doc classification | Good | `readme`, `spec`, `design`, `domain`, `adr`, `runbook`, `incident`, `api_contract` |
| Docs-aware retrieval | Good | `docs-for --mode/--type`, typed doc boosts trong `context-for` |
| Drift detection | Partial | `doc-drift` da co query-time heuristic cho stale/missing/weak docs, chua co full-repo audit hay semantic drift |

## Evals

| Capability | Current | Notes |
| --- | --- | --- |
| Repeatable retrieval eval | Good | `system-wiki eval` + suite assertions |
| Baseline compare | Good | `--compare-baseline` + delta reporting |
| Baseline maintenance | Partial | `--update-baseline-if-better` da co, chua co CI wiring |
| Time-to-edit metrics | Not started | chua do duoc `time to first useful edit` |
