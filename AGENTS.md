# AGENTS.md

## Project

Hammer Jarvis is a local Windows-first personal AI assistant backend.

The first version connects to Home Assistant through the REST API and exposes a local FastAPI interface.

## Core Rules

- Keep the project local-first.
- Do not add cloud deployment.
- Do not add Docker yet.
- Existing local browser-based voice recognition and speech output may be maintained or improved.
- Do not add external or cloud-based TTS/STT services without explicit approval.
- Do not add PLC write functions.
- Do not add OpenAI API calls yet.
- Do not hardcode secrets.
- Use `.env` for local configuration.
- Create `.env.example`, but never create a real `.env` with secrets.
- Use Python 3.11 or newer.
- Keep dependencies minimal.
- Use readable, small modules.
- Add clear error handling.
- Add German README instructions for Windows PowerShell.
- Do not expose tokens in logs or API responses.

## Dependencies

Use these dependencies for v0.1:

- FastAPI
- Uvicorn
- requests
- python-dotenv
- pydantic
- pytest

Do not add LangChain for v0.1.
Do not add a database for v0.1.
Do not add unnecessary abstraction.
The existing local dashboard may be maintained or improved.

## Permission Model

Every external device control action must go through a permission layer.

Permission levels:

- GREEN: Home Assistant read operations.
- YELLOW: Home Assistant write operations. These require confirmation.
- RED: PLC write actions, deleting files, sending emails, and production-relevant actions.

RED actions must not be implemented in v0.1 unless explicitly requested later with a revised safety design.

## Audit Logging

Log relevant actions to:

```text
app/logs/audit.log
```

Audit logs should include meaningful action context, timestamps, permission level, and outcome.

Never log secrets, tokens, or sensitive authorization headers.

## Coding Style

- Use type hints where useful.
- Use clear names.
- Prefer straightforward Python modules over framework-heavy patterns.
- Keep functions small and readable.
- Handle network, configuration, and permission errors clearly.
- Return safe error responses without leaking tokens or internal secrets.

## Local Configuration

Use environment variables loaded from `.env` through `python-dotenv`.

Provide `.env.example` with placeholder values only.

Never commit or generate a real `.env` containing secrets.

## Home Assistant

Home Assistant integration should use the REST API.

Read operations are GREEN.

Write operations are YELLOW and must require explicit confirmation through the permission layer before execution.

Responses and logs must not reveal the Home Assistant token.

## Windows Development

The project is developed for local Windows usage first.

README setup and run instructions must be written in German and use Windows PowerShell examples.
