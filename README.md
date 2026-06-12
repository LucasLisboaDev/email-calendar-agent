# Email & Calendar Automation Agent

An agentic AI system that automates email sorting, smart replies, and meeting scheduling using Gmail API, n8n, and GPT-4o.

## Project phases

| Phase | What it does | Status |
|-------|-------------|--------|
| 1 | Gmail ingestion — OAuth, fetch, parse emails | 🔨 In progress |
| 2 | Orchestration — n8n workflows, routing logic | ⏳ Upcoming |
| 3 | AI reasoning — GPT-4o function calling, classification | ⏳ Upcoming |
| 4 | Smart actions — send replies, schedule meetings | ⏳ Upcoming |
| 5 | Eval & observability — logging, tracing, feedback loop | ⏳ Upcoming |

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/LucasLisboaDev/email-calendar-agent.git
cd email-calendar-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add credentials

- Download `credentials.json` from Google Cloud Console
- Drop it in the project root (never commit this file)
- Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### 3. Run Phase 1 test

```bash
python main.py
```

On first run, a browser window will open for Gmail login. After approving, `token.json` is saved and future runs are silent.

## Project structure

```
email-calendar-agent/
├── credentials.json        ← Google OAuth credentials (never commit)
├── token.json              ← Auto-generated after first login (never commit)
├── .env                    ← Your environment variables (never commit)
├── .env.example            ← Template for .env
├── .gitignore
├── requirements.txt
├── main.py                 ← Entry point
├── auth/
│   └── gmail_auth.py       ← OAuth 2.0 flow, token management
├── ingestion/
│   └── gmail_reader.py     ← Fetch and parse emails from Gmail
├── agent/                  ← Phase 3: GPT-4o reasoning (coming soon)
├── actions/                ← Phase 4: send replies, book meetings (coming soon)
└── utils/
    ├── logger.py           ← Centralized loguru logging
    └── email_models.py     ← Pydantic data models
```

## Key concepts

- **OAuth 2.0** — User grants permission once; refresh token handles re-auth automatically
- **Agentic loop** — Reason → Act → Observe → repeat (ReAct pattern)
- **Function calling** — GPT-4o returns structured JSON tool calls, not freeform text
- **Human-in-the-loop** — Agent drafts actions; human approves before execution
- **Observability** — Every run is logged with trace IDs for debugging and eval

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CREDENTIALS_PATH` | Path to credentials.json | `credentials.json` |
| `GOOGLE_TOKEN_PATH` | Path to save token.json | `token.json` |
| `OPENAI_API_KEY` | Your OpenAI API key | — |
| `EMAIL_FETCH_LIMIT` | Emails to fetch per run | `10` |
| `EMAIL_LABEL` | Gmail label to watch | `INBOX` |
| `HUMAN_APPROVAL_REQUIRED` | Require approval before actions | `true` |
# Phase 4 active
