# Dough Credit Union — Member Services Portal

Local mock of an internal member-investigation portal. It is **not** a production banking system and does not move money.

## Stack

- Python 3.11+
- FastAPI, Jinja2, SQLAlchemy 2, SQLite
- Server-side sessions, CSRF on every mutating POST, bcrypt password hashes

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.seed
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Deploy on Vercel

GitHub stores the code; Vercel runs it as one Python function. A private GitHub repo works if you import it while logged into Vercel (the repo does not need to be public).

```bash
npx vercel@latest login
npx vercel@latest --prod
```

In the Vercel project, set:

- `SESSION_SECRET` — a long random string (required)
- `DEV_SCENARIOS_ENABLED` — `true` if you want `/dev/scenarios`

SQLite cannot persist on Vercel’s serverless filesystem. The build seeds a snapshot, and each function instance copies it to `/tmp`. Logins, notes, and scenario flags can reset when that instance is replaced. This is a demo host, not a durable database.

Employee usernames and passwords are printed **only** by the seed command in your terminal. They are not listed in this repository's documentation. Re-run `python -m app.seed` if you need them printed again.

## Configuration

`.env.example` includes:

- `DATABASE_URL` — default SQLite file `bank.db` (gitignored)
- `SESSION_SECRET` — used to sign the session cookie; change it locally
- `DEV_SCENARIOS_ENABLED` — when `true`, `/dev/scenarios` is available for fault injection
- `SESSION_TTL_HOURS` — server-side session lifetime

Copy `.env.example` to `.env` and adjust as needed. `/dev/scenarios` is omitted from product navigation and returns 404 unless the flag is enabled.

## Tests

```bash
pytest
```

## Reset

Seeding is deterministic (fixed member IDs, fixture transactions, and a large generated history).

```bash
python -m app.seed --reset
```

`--reset` **deletes local demonstration data** in the configured database and restores the seed. The Reset control on `/dev/scenarios` does the same thing and also clears scenario flags.

See [DEMO.md](DEMO.md) for sample investigation tasks and expected seed IDs.
