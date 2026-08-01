# Database Migration Runbook (Render free Postgres expiry)

Render's free PostgreSQL databases have a fixed lifetime and get deleted
once it's up — this is separate from the web service itself, which does
**not** expire (it only sleeps when idle). When Render warns the database
is about to be deleted, follow this runbook to move onto a fresh free
database without losing data or touching anything else (hostname, Google
OAuth, Brevo, uploaded media files all stay exactly as they are, since only
the database connection is being swapped).

Run all commands from the project root, in the same local venv already used
for `python manage.py test`.

## 1. Create the new database

Render dashboard → **New → PostgreSQL** → free tier → same region as the
existing web service. Once created, open its **Connect** tab and note:

- **External Database URL** — used below, from your local machine
- **Internal Database URL** — used later, by the web service itself

## 2. Back up data from the OLD database

```powershell
$env:DATABASE_URL = "<OLD external database URL>"
python manage.py dumpdata --natural-foreign --natural-primary `
  -e contenttypes -e auth.permission -e admin.logentry -e sessions.session `
  -o backup_render_YYYY-MM-DD.json
```

Sessions are excluded on purpose — they invalidate on cutover anyway, so
everyone just logs in again (expected, not a bug). `backup_render_*.json` is
already gitignored for exactly this kind of one-off dump — never commit it.

## 3. Build schema + restore data into the NEW database

```powershell
$env:DATABASE_URL = "<NEW external database URL>"
python manage.py migrate
python manage.py loaddata backup_render_YYYY-MM-DD.json
```

## 4. Reset Postgres sequences

`loaddata` restores explicit primary keys, which leaves each table's
auto-increment counter behind — the next `.objects.create()` could then
collide with an existing row. Still pointed at the **new** database:

```powershell
python manage.py sqlsequencereset accounts appointments records notifications feedback
```

Pipe the printed SQL into the new database (`psql` if you have it locally).
No `psql`? Run the statements instead from `python manage.py shell` via
`django.db.connection.cursor().execute(...)` — no local Postgres client
needed either way.

## 5. Verify row counts match

Before touching production, compare counts between old and new (swap
`$env:DATABASE_URL` between checks) — e.g. `CustomUser.objects.count()`,
`Appointment.objects.count()`, `SocialAccount.objects.count()`.

## 6. Cut the live web service over

Render dashboard → the web service → **Environment** → change
`DATABASE_URL` to the **new** database's **Internal** Database URL → Save.
This triggers an automatic redeploy/restart.

## 7. Smoke test the live site

- Admin login + `/django-admin/accounts/customuser/` (the page that needed
  the Python 3.13+ compatibility patch in `accounts/apps.py`)
- Patient / doctor / secretary dashboards
- Booking an appointment end to end
- Google sign-in round trip
- GitHub Actions reminder workflow — run it manually via `workflow_dispatch`
  in the Actions tab rather than waiting for the nightly schedule

## 8. Do not delete the old database

Leave it running, untouched, as a rollback path (just flip `DATABASE_URL`
back if something's wrong) for at least a few days past whatever prompted
this migration. Only delete it — or let it expire naturally — once you're
confident the new one is solid.
