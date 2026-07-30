# Hazard Family Reunion 2026

Itinerary and meal-RSVP site for the Hazard family reunion, August 1–8, 2026.

## Public site

- `index.html` — mobile-friendly itinerary, maps, and safety notes.
- `rsvp/index.html` — meal RSVP instructions, live Google Form link, and personal backup builder.
- `config.js` — public runtime configuration and the small `/edit` / `/admin` footer links.
- `create_hazard_rsvp_form.gs` — creates the household meal RSVP form, response spreadsheet, and live per-meal headcounts.
- `deploy/deploy.sh` — copies only public static files into the Nginx document root.

Production URL: `https://taylorarchibald.com/reunion/`

## SSO-protected editing

The repository also contains a small Flask service for:

- `/reunion/rsvp/` — meal RSVP page with the live Google Form and estimate-only backup builder.
- `/reunion/edit` — in-place visual editing of the rendered itinerary. Text can be edited directly; itinerary sections and events can be added, moved, or deleted.
- `/reunion/admin` — a chat-only shell for a persistent Codex session scoped to this repository.
- `/reunion/api/` — authenticated document, publish, audit, and Codex-turn endpoints.

The service validates the existing webapps `universal_sso_token` cookie using the shared `SSO_JWT_SECRET`. Authorized accounts are configured with `REUNION_ADMIN_USERS`. A user already signed into another `taylorarchibald.com` sister app should not be asked to sign in again.

The public page stays static. Nginx proxies only `/reunion/edit`, `/reunion/admin`, `/reunion/api/`, `/reunion/health`, and `/reunion/sso/login` to the local service.

### Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt
REUNION_AUTH_DISABLED=true \
REUNION_DATA_ROOT=/tmp/reunion-data \
waitress-serve --listen=127.0.0.1:13041 --call server.app:create_app
```

In a second terminal, serve the public page on the same origin through a local reverse proxy, or use the Nginx example in `deploy/nginx-location.conf.example`. The visual editor intentionally loads `/reunion/` in a same-origin iframe.

## Production environment

The systemd service should load:

```text
SSO_JWT_SECRET=<same protected value used by webapps SSO>
REUNION_ADMIN_USERS=tahlor@gmail.com,tahlor
REUNION_REPO_ROOT=/home/ubuntu/Projects/reunion
REUNION_DATA_ROOT=/home/ubuntu/webapps_data/reunion
REUNION_CODEX_RUNNER=/home/ubuntu/webapps_data/reunion/codex_runner.sh
REUNION_SECRET_KEY=<independent random secret>
```

Use `deploy/reunion-admin.service.example` as the unit template. Keep the environment, Codex session, audit log, document backups, and runner outside Git and outside the public document root.

### Publishing from the visual editor

The editor:

1. checks that the dedicated checkout is clean and still on `master`;
2. validates Hazard branding and rejects unsafe markup and URLs;
3. creates a private backup;
4. writes `index.html` atomically;
5. runs `deploy/publish.sh`, which fetches `origin/master`, commits the page change directly to `master`, pushes it, and deploys the static site.

The service must run as a user that can write to the repository checkout, push `Tahlor/reunion`, and run `deploy/deploy.sh`. Do not grant the Nginx worker account Git credentials.

The organizer can review submitted meal counts from the SSO-protected Admin chat page. After running the Apps Script, put the private response-spreadsheet URL in `REUNION_RSVP_RESULTS_URL` in the host-only `reunion.env`; the admin page will show `Review RSVP results` without publishing that link or any response data to the public site.

### Codex runner contract

`REUNION_CODEX_RUNNER` must point to a fixed executable that:

- reads one chat message from standard input;
- works only in `REUNION_REPO_ROOT`;
- resumes one durable Codex session stored under `REUNION_CODEX_SESSION_DIR`;
- prints the assistant-facing response to standard output;
- never treats browser input as a shell command.

`deploy/codex_runner.example.sh` documents the contract. The Archimedes agent must wire it to the installed Codex CLI/SDK version or reuse the existing `webapps/codex_apps` session machinery.

## Meal RSVP form

1. Open `https://script.new` in the Google account that owns the existing form.
2. Paste `create_hazard_rsvp_form.gs` into the editor and run `updateHazardMealRsvp` to rebuild the existing form with one estimate-only 0–12 portion field plus six meal attendance choices.
3. The form’s `Meal Totals` sheet sums estimated adult-sized portions for attending households. These are planning numbers, not a food guarantee.
4. The public form URL belongs in `config.js`; keep the response-spreadsheet URL in the host-only `REUNION_RSVP_RESULTS_URL` environment variable so the Admin page can review results privately.
