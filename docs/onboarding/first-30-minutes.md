# First 30 Minutes In `system-wiki`

Tai lieu nay danh cho mot developer moi vao repo va muon nhanh chong:

- biet nen doc file nao truoc
- biet entrypoint nao dang dieu phoi he thong
- biet neu muon phat trien tiep thi nen chon diem mo rong nao

Guide nay duoc rut ra tu viec chay `system-wiki` tren chinh repo `system-wiki`.

## Muc tieu trong 30 phut

Sau 30 phut, ban nen tra loi duoc 3 cau hoi:

1. CLI bat dau tu dau?
2. Pipeline build graph di qua nhung khoi nao?
3. Neu muon sua query/navigation thi file nao can canh chung?

## Minute 0-5: Nhin tu tren xuong

Doc:

- `README.md`
- `CODEBASE_UNDERSTANDING_PLAN.md`
- `docs/roadmap/progress-checklist.md`

Muc tieu:

- hieu project nay la mot context engine cho coding agents
- hieu 4 cau hoi lon ma roadmap dang toi uu:
  - code o dau
  - no lam gi
  - no lien quan toi gi
  - sua no se anh huong gi

## Minute 5-10: Tim entrypoint chinh

Chay:

```bash
system-wiki query entrypoints
```

Ket qua quan trong tren chinh repo:

- `main()` trong `system_wiki/__main__.py`
- `query_main()` trong `system_wiki/query_graph.py`
- module `system_wiki/__main__.py`

Cach doc:

- bat dau tu `system_wiki/__main__.py` de hieu routing CLI
- sau do sang `system_wiki/query_graph.py` de hieu query surface

## Minute 10-20: Theo pipeline build graph

Doc theo thu tu:

1. `system_wiki/__main__.py`
2. `system_wiki/detect_files.py`
3. `system_wiki/extract_public_api.py`
4. `system_wiki/build_graph.py`
5. `system_wiki/extract_cross_reference.py`
6. `system_wiki/module_graph.py`
7. `system_wiki/query_graph.py`

Mau mental model nen giu:

- `__main__.py`: nhan lenh va dieu phoi build/query/eval
- `detect_files.py`: quyet dinh file nao duoc dua vao pipeline
- `extract_public_api.py`: dispatch parser theo ngon ngu va enrich symbol metadata
- `build_graph.py`: hop nhat nodes/edges thanh graph
- `extract_cross_reference.py`: noi code voi docs va reference heuristic
- `module_graph.py`: tao lop nhin theo module/dependency
- `query_graph.py`: bien graph thanh cac query co y nghia cho developer

## Minute 20-25: Dung query de tu kiem tra hieu biet

Chay:

```bash
system-wiki query context-for --mode onboarding "Mình cần hiểu nhanh kiến trúc và các file quan trọng để bắt đầu phát triển system-wiki"
```

Tren repo hien tai, cac file duoc surface manh gom:

- `system_wiki/detect_files.py`
- `system_wiki/cache_file_hash.py`
- `system_wiki/__main__.py`
- `system_wiki/extract_public_api.py`
- `README.md`

Dieu nay cho thay:

- phan scan/classify file la trung tam cua pipeline
- caching va extraction dispatch la hai diem quan trong de toi uu toc do va do chinh xac

## Minute 25-30: Chon diem vao de phat trien

Neu ban muon mo rong navigation/query cho nhieu language hon, chay:

```bash
system-wiki query files-for-change "Thêm hỗ trợ references/definitions ổn định hơn cho nhiều ngôn ngữ ngoài Python"
system-wiki query verify-after-change --mode feature "Thêm hỗ trợ references/definitions ổn định hơn cho nhiều ngôn ngữ ngoài Python"
```

Ket qua tren repo hien tai goi y:

- sua truoc: `system_wiki/extract_python_postprocess.py`, `system_wiki/query_graph.py`
- kiem tra ke ben: `system_wiki/extract_public_api.py`, `system_wiki/__main__.py`
- test nen xem: `tests/test_context_for.py`

Neu ban dinh sua `query_graph.py`, nen chay them:

```bash
system-wiki query impact query_graph.py
system-wiki query semantics query_graph.py
system-wiki query graph-diff wiki-out/graph-before.json
```

Vi file nay dang co `risk: high` va lien quan truc tiep den:

- `system_wiki/__main__.py`
- `system_wiki/eval_benchmarks.py`
- `tests/test_context_for.py`

## Reading Order De Xuat

Neu chi co 30 phut, doc theo thu tu nay:

1. `README.md`
2. `system_wiki/__main__.py`
3. `system_wiki/detect_files.py`
4. `system_wiki/extract_public_api.py`
5. `system_wiki/query_graph.py`
6. `docs/roadmap/progress-checklist.md`
7. `docs/issues/README.md`

## Lenh nen nho

```bash
system-wiki .
system-wiki query stats
system-wiki query entrypoints
system-wiki query context-for --mode onboarding "<task>"
system-wiki query files-for-change "<task>"
system-wiki query verify-after-change --mode feature "<task>"
system-wiki query impact query_graph.py
system-wiki query semantics query_graph.py
system-wiki query graph-diff wiki-out/graph-before.json
system-wiki eval
```

## Sau 30 Phut Nen Lam Gi?

Lua chon hop ly nhat de bat dau implementation:

- ISSUE-002 neu muon lam navigation/symbol identity tot hon
- ISSUE-005 neu muon lam dependency/flow sau hon
- ISSUE-008 neu muon toi uu `context-for` va giam token
- ISSUE-009 neu muon nang chat luong benchmark va regression gate
