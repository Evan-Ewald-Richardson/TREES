# Secret Gates Race (personal prototype)

This is a personal project exploring a fun **race format**. It’s a playground to test ideas before anything public.

## What it does
- Lets you **upload GPS routes** (GPX files) and see them on a map.
- You can place **gate pairs** (start/end points) to define “segments.”
- Save a set of gates as a **course** and load it later.
- Post your run to a simple **leaderboard**.

## How to use (non-technical)
1. Open the app and **upload** your GPX file(s).
2. Add **gate pairs** on the map, then **save** them as a course.
3. **Load** a course to check it.
4. If your route passes the gates in order, **submit** your time to the leaderboard.

— Evan

## Resetting the database (one-time schema refresh)

The backend stores data in `data/app.db` (SQLite). If you deploy a schema change
and need a clean database, start the API once with `DB_RESET=1`:

```bash
DB_RESET=1 uvicorn backend.app:app --reload
```

This drops and recreates all tables. **Remove the environment variable after the
reset** so regular runs do not wipe your data. As an alternative, you can delete
`data/app.db` manually before starting the server.
