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

[buildpack]: https://devcenter.heroku.com/articles/python-support
