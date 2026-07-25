# Deployment — Heroku (web UI)

The app runs on Heroku with the [Python buildpack][buildpack]. Continuous
integration (lint + tests + coverage) runs on GitHub Actions (`.github/workflows/ci.yml`);
Heroku deploys automatically once CI-verified code lands on the tracked branch.

## Runtime manifest (already in the repo)

| File | Purpose |
|------|---------|
| `Procfile` | `web:` runs gunicorn; `release:` runs migrations on every deploy |
| `.python-version` | Pins Python 3.12 for the buildpack |
| `app.json` | Declares the Postgres add-on and required config vars |
| `requirements.txt` | Runtime deps (gunicorn, whitenoise, dj-database-url, psycopg2) |

## One-time setup (Heroku Dashboard)

1. **Create the app** — *New → Create new app*, pick a name and region.
2. **Connect GitHub** — *Deploy* tab → *Deployment method: GitHub* → connect the
   repository.
3. **Enable Automatic Deploys** — on the *Deploy* tab, choose the `dev` branch
   (or `main`) and tick **Wait for CI to pass before deploy**, then
   *Enable Automatic Deploys*. Every merge to that branch now redeploys once the
   GitHub Actions CI check is green.

## Config vars (Settings → Reveal Config Vars)

Set these **before the first deploy** — the build runs `collectstatic` and the
release phase runs `migrate`, and `config.settings.prod` fails fast if the
secrets are missing.

| Key | Value |
|-----|-------|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DOCUMENT_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ALLOWED_HOSTS` | `your-app-name.herokuapp.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app-name.herokuapp.com` |
| `DEBUG` | `False` (or leave unset — defaults to False) |

`DATABASE_URL` is set automatically by the Postgres add-on (see below).

## Data stores

### Postgres (provisioned)

*Resources* tab → add **Heroku Postgres** (`essential-0` tier is enough for the
MVP). Heroku injects `DATABASE_URL`, which `config/settings/base.py` reads via
`dj-database-url` — no code change needed to switch from local SQLite to cloud
Postgres. `app.json` declares this add-on so a *Deploy to Heroku* provision
attaches it automatically.

### Document storage (encrypted, on-dyno)

Uploaded documents are Fernet-encrypted at rest by
`documents.storage.EncryptedFileSystemStorage` (M6). **Heroku's filesystem is
ephemeral** — files written by a dyno do not survive a restart or redeploy, so
on-dyno storage is only appropriate for a demo/MVP deploy.

## Build & release lifecycle

Nothing here is manual — each deploy runs it automatically:

1. **Build** — the Python buildpack installs `requirements.txt` and runs
   `manage.py collectstatic --noinput`. Static files are served by
   **WhiteNoise** (`whitenoise.storage.CompressedManifestStaticFilesStorage`),
   so no separate static host or CDN is required.
2. **Release** — the `Procfile` `release:` line runs `manage.py migrate --noinput`
   against the provisioned Postgres before the new dynos go live. (`app.json`'s
   `postdeploy` covers the same for one-click provisions.)
3. **Run** — `web: gunicorn config.wsgi` serves the app; TLS is terminated at the
   Heroku router and forwarded via `X-Forwarded-Proto`, which `prod.py` honours
   for `SECURE_SSL_REDIRECT`.

Secrets never live in the repo (`.env` is gitignored) — they are Heroku config
vars only, and `config.settings.prod` refuses to boot if `SECRET_KEY` or
`DOCUMENT_ENCRYPTION_KEY` is missing.

For durable storage, swap the storage backend for S3 (or another object store)
without touching the models, views, or access checks: point
`EncryptedFileSystemStorage` at an S3 base (or subclass Django's S3 storage),
add the bucket credentials as config vars, and downloads keep flowing through
the same access-checked `download_document` view. That swap is the M6 design
seam and is deliberately left as a follow-up.

[buildpack]: https://devcenter.heroku.com/articles/python-support
