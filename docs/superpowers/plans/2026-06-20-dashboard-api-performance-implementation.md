# Dashboard API Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce dashboard request volume, duplicate API calls, and unnecessary DOM work without changing voice, wake, chat, or WebSocket behavior.

**Architecture:** Split the all-panels refresh into fast, normal, and slow refresh groups. Add an in-flight GET promise map for concurrent identical reads and avoid DOM writes when displayed text has not changed. Manual actions stay immediate.

**Tech Stack:** Vanilla JavaScript, FastAPI existing endpoints, pytest.

---

## File Structure

- Modify `app/static/dashboard.js`: scheduling, request de-duplication, DOM guards, timer cleanup.
- Modify `tests/test_api.py`: regression tests for scheduling and preserved voice/WebSocket entry points.
- Modify `README.md`: German note on refresh tiers and local resource behavior.

### Task 1: Split the refresh workload

**Files:** `app/static/dashboard.js`, `tests/test_api.py`

- [ ] Write `test_dashboard_uses_bounded_refresh_tiers` asserting `dashboardFastRefreshMs`, `dashboardNormalRefreshMs`, `dashboardSlowRefreshMs`, `refreshDashboardFast`, `refreshDashboardNormal`, and `refreshDashboardSlow`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py::test_dashboard_uses_bounded_refresh_tiers -q`; expect failure.
- [ ] Add intervals of 10 seconds for EcoFlow, Home Assistant, and pending actions; 30 seconds for system status, alerts, recent files, Gmail, and TimeTree; and 120 seconds for entity catalog, Smart Home policy, control policy, memory, knowledge, and performance.
- [ ] Keep `refreshDashboard()` as the initial coordinator calling all three groups once. Store interval IDs after initial load instead of creating another all-panels 30-second interval.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`; expect pass.

### Task 2: Deduplicate non-interactive GET requests

**Files:** `app/static/dashboard.js`, `tests/test_api.py`

- [ ] Write `test_dashboard_deduplicates_identical_get_requests` asserting `const inFlightGetRequests = new Map()`, `inFlightGetRequests.get(url)`, and `inFlightGetRequests.delete(url)`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py::test_dashboard_deduplicates_identical_get_requests -q`; expect failure.
- [ ] Add `inFlightGetRequests`. In `fetchJson`, return an existing request only for GET calls without `activityId`; create a request through `requestJson`, store it, and remove it in `finally`.
- [ ] Keep POST requests and requests carrying an activity ID outside the shared promise map so interactive button feedback remains independent.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`; expect pass.

### Task 3: Avoid no-op DOM writes and clean timers

**Files:** `app/static/dashboard.js`, `tests/test_api.py`

- [ ] Write `test_dashboard_guards_dom_updates_and_cleans_refresh_timers` asserting `dashboardRefreshTimers`, `cleanupDashboardTimers`, the pagehide cleanup registration, and `elements[id].textContent === next`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py::test_dashboard_guards_dom_updates_and_cleans_refresh_timers -q`; expect failure.
- [ ] Change `setText` to compare the next string with current `textContent` before assigning it.
- [ ] Add `dashboardRefreshTimers` and `cleanupDashboardTimers`; clear every scheduled refresh interval during existing `pagehide` and `beforeunload` handling before closing the desktop socket.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`; expect pass.

### Task 4: Preserve interactive integrations and document behavior

**Files:** `tests/test_api.py`, `README.md`

- [ ] Add a test asserting `new WebSocket(buildDesktopEventSocketUrl())`, `startCommandRecognition({ source: "button", autoSend: true })`, and `source: "desktop_agent"` remain in dashboard JavaScript.
- [ ] Add a German README note stating that quick, normal, and slow dashboard data use separate intervals and identical simultaneous GET calls are merged locally.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`; expect all tests to pass.
- [ ] Run `.\.venv\Scripts\python.exe -m compileall app`; expect success.
- [ ] Run `git diff --check`; expect no output.

### Task 5: Validate PowerShell scripts

**Files:** `scripts/*.ps1`

- [ ] Parse every PowerShell script with `[System.Management.Automation.Language.Parser]::ParseFile`.
- [ ] Expect output `PowerShell parser OK`.

## Plan Self-Review

- Stage 1 coverage includes scheduling, duplicate API requests, DOM update churn, timer cleanup, and preservation of wake/voice/WebSocket behavior.
- Names are consistent: `dashboardRefreshTimers`, `inFlightGetRequests`, `refreshDashboardFast`, `refreshDashboardNormal`, and `refreshDashboardSlow`.
- No commits are included because the workspace explicitly prohibits commits and pushes.
