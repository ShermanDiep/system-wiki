# Evals And Benchmark Tasks

Muc tieu cua bo eval nay la do chat luong retrieval/context theo cach lap lai duoc.

## Metrics khoi dau

- `context recall`: trong cac file/doc mong doi, he thong lay duoc bao nhieu
- `context precision`: trong cac file/doc he thong tra ve, ti le dung la bao nhieu
- `avg files opened`: moi task mo ra bao nhieu file context
- `avg approx tokens`: xap xi do dai output query, dung lam token proxy local
- `assertions`: nguong toi thieu/toi da de bien eval thanh regression gate

## Starter cases

### 1. Feature work tren `query_graph.py` / `module_graph.py`

Task:

`task-aware path ranking and context assembly in query_graph and module_graph`

Expect:

- `context-for` phai surface `system_wiki/query_graph.py`
- `context-for` phai surface `system_wiki/module_graph.py`
- `files-for-change` phai dua 2 file tren vao `Edit first`
- `files-for-change` phai dua `system_wiki/__main__.py`, `system_wiki/export_json.py`, `system_wiki/report_markdown.py` vao `Verify adjacent code`

### 2. Refactor work tren `query_graph.py`

Task:

`refactor query_graph context assembly and module ranking`

Expect:

- `files-for-change` phai dua `system_wiki/query_graph.py` vao `Edit first`
- `files-for-change` phai dua `system_wiki/__main__.py` vao `Verify adjacent code`

### 3. Docs lookup cho entrypoint chinh

Task:

`docs-for --mode onboarding --type readme main`

Expect:

- phai lay duoc `README.md`
- `README.md` phai duoc uu tien nhu mot `readme` doc type
- precision da duoc siet hon nho typed doc classification

### 4. Untested impact cho `query_graph.py`

Task:

`untested-impact query_graph.py`

Expect:

- phai flag `system_wiki/__main__.py` nhu mot dependent chua thay test mapping ro

### 5. Doc drift cho entrypoint chinh

Task:

`doc-drift --mode onboarding --type readme main`

Expect:

- phai surface `README.md` trong `Suggested docs to review`
- co the bao `Weak doc-code links` neu readme chi dang duoc noi bang overview/community thay vi direct link
- precision khong can perfect vi co the cung luc surfacing `docs/issues/README.md`

### 6. Verify checklist cho feature work

Task:

`verify-after-change --mode feature "task-aware path ranking and context assembly in query_graph and module_graph"`

Expect:

- `Verify adjacent code` phai gom `system_wiki/__main__.py`, `system_wiki/export_json.py`, `system_wiki/report_markdown.py`
- `Smoke likely entry paths` phai quay ve `system_wiki/query_graph.py`
- `Untested impact watchlist` phai nhac lai 3 file dependent tren

## Run

```bash
system-wiki eval
system-wiki eval docs/evals/context-engine-starter.json
system-wiki eval --json
system-wiki eval --write-baseline docs/evals/baseline.json
system-wiki eval --compare-baseline docs/evals/baseline.json
system-wiki eval --update-baseline-if-better docs/evals/baseline.json
system-wiki query doc-drift --mode feature query_graph.py
```

Luu y:

- Day la starter suite nho de khoa regression cho context engine hien tai.
- `system-wiki eval` se return exit code `1` neu assertion trong suite bi fail.
- `--update-baseline-if-better` chi ghi de baseline khi run hien tai pass va khong te hon baseline cu.
- Khi query surface thay doi hoac repo doi huong, can cap nhat expectations thay vi de suite stale.
