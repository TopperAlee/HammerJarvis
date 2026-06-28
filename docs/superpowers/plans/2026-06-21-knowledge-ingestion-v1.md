# Knowledge Ingestion v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Tasks use checkbox syntax for tracking.

**Goal:** Add safe local document upload, persistent keyword indexing, automatic bounded knowledge context, and dashboard document management.

**Architecture:** Keep the JSON index and lexical search for v1. Store upload files outside the repository under LOCALAPPDATA, protect writes with a process lock and atomic replacement, and keep external/local-path documents distinct. Document paths never enter LLM prompts; only display names and chunk excerpts do.

**Tech Stack:** FastAPI, python-multipart, pypdf, python-docx, openpyxl, vanilla JavaScript, pytest.

---

### Task 1: Storage, security, and KnowledgeStore
- [x] Add safe LOCALAPPDATA defaults, upload storage, SHA-256 document identity, metadata, atomic JSON writes, recovery, locking, delete, and reindex.
- [x] Preserve existing local-path indexing and prevent deleting files whose source type is `local_path`.

### Task 2: Document extraction
- [x] Add structured CSV/XLSX/XLSM/DOCX extraction, PDF textless `ocr_required`, and safe read-only macro-free XLSM handling.

### Task 3: API
- [x] Add multipart multiple-upload, document detail, reindex, and delete routes while keeping status/search/list compatible.

### Task 4: Automatic knowledge context
- [x] Add bounded context builder and integrate it with normal LLM messages, including returned `knowledge_sources` but no local paths in prompts.

### Task 5: Dashboard
- [x] Add local upload controls, per-file status, list actions, and compact chat source display without changing voice/WebSocket behavior.

### Task 6: Tests and integration
- [ ] Run security, storage, API, orchestration, dashboard regression, full test, compile, diff, and PowerShell parser checks.

## Constraints

- No external upload or OCR.
- No macro execution.
- No database, LangChain, or vector search in v1.
- No commit or push.
