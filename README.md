# Agentic Hotel System (ADK-First MVP)

## 1. Environment Baseline (Required)

All Python commands must run inside `Final/venv`.

### Windows

```powershell
cd "d:\Documents\UniMAP\Gemini Nexus\Final"
python -m venv venv
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Verify interpreter

```powershell
.\venv\Scripts\python.exe -c "import sys; print(sys.prefix)"
```

Expected prefix includes `Final\venv`.

## 2. Secrets and Config

1. Copy `.env.example` to `.env`.
2. Set:
- `GOOGLE_API_KEY`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SHEETS_CREDENTIALS_FILE` (default points to bundled service-account json file)

Do not hardcode secrets in source files.

## 3. Start Services

### MCP Tool Server

```powershell
.\venv\Scripts\python.exe tools\mcp_server.py
```

### FastAPI Backend

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

## 4. API Endpoints

- `POST /chat`
- `POST /booking`
- `GET /rooms`
- `POST /payment`
- `POST /complaint`

## 5. Guardrail Lifecycle

`User Request -> Input Guard -> Root Orchestrator -> Policy Guard -> Agent Execution -> Tool Guard -> MCP Tool Call -> Output Guard -> Response`

## 6. Tests

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Current suite includes schema validation and mandatory guardrail attack tests.

## 7. Minimal Frontend Scaffold

Laravel-oriented minimal chat scaffold is under `app/` with:
- `app/routes/web.php`
- `app/app/Http/Controllers/ChatController.php`
- `app/resources/views/chat.blade.php`
- `app/public/js/chat.js`

Connect Laravel base URL to FastAPI using `FASTAPI_BASE_URL` in Laravel env.
