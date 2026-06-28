# Performance and Resource Optimization Design

## Scope

Optimize Hammer Jarvis in three ordered stages without changing safety behavior,
the existing WebSocket route, Windows Speech recognition, or local-first
constraints.

## Stage 1: Dashboard and API Load

- Keep one refresh in flight at a time.
- Split fast status data from slower data sets and refresh slower data less often.
- Avoid rendering unchanged dashboard values.
- Ensure interval and WebSocket heartbeat cleanup remains bounded on page unload.
- Add targeted tests for request scheduling and cleanup behavior where practical.

Success criteria:

- Fewer concurrent dashboard requests.
- No duplicate dashboard WebSocket connection.
- Existing chat, manual speech, and wake event behavior stays unchanged.

## Stage 2: File and OneDrive Search

- Preserve allowed-directory and path-safety rules.
- Stop recursive scans on configured time, depth, and result limits.
- Prioritize filename and path matches before content extraction.
- Reuse bounded metadata and extraction caches for unchanged files.
- Report skipped files and timeout conditions clearly without failing whole searches.

Success criteria:

- Lower filesystem and OneDrive sync-folder I/O.
- Faster common filename searches.
- No search outside configured allowed directories.

## Stage 3: LLM and Orchestrator Runtime

- Keep deterministic tool-first routes ahead of LLM use.
- Reuse lightweight local clients where existing architecture allows it.
- Bound prompt context and pass only data relevant to the active route.
- Avoid repeated provider/status checks during a single request.
- Retain rule-based fallbacks and all confirmation requirements.

Success criteria:

- Lower Ollama request latency and context size.
- No invented data when local tool data exists.
- Gmail, TimeTree, EcoFlow, Home Assistant, files, and dashboard voice remain compatible.

## Measurement and Validation

- Use existing performance metrics where possible.
- Add focused metrics only when they inform an optimization decision, such as cache
  hit rate, scan stop reason, request duration, or prompt size.
- Run targeted tests after each stage, then the full test suite, compileall,
  git diff --check, and PowerShell parser validation.

## Boundaries

- No cloud deployment, database, Docker, or global package installation.
- No raw audio storage or logging.
- No changes to the functioning desktop wake listener or WebSocket route contract.
- No deletion, overwriting, or broad filesystem scans beyond existing allowed paths.
