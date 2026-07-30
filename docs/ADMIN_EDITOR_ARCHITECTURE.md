# Reunion admin/editor architecture

The public itinerary remains a static Nginx site. A local Flask service handles only SSO-protected editing and administration.

## Routes

- `/reunion/` — public static itinerary
- `/reunion/rsvp/` — public static RSVP page
- `/reunion/edit` — visual in-place editor
- `/reunion/admin` — Codex chat interface
- `/reunion/api/document` — load and publish the editable `<main>` content
- `/reunion/api/codex/*` — persistent chat turn queue
- `/reunion/health` — service health check

## Authentication

The service verifies the same `universal_sso_token` JWT cookie issued by `Tahlor/webapps/sso`. The cookie is scoped to `.taylorarchibald.com`, so a browser already signed into a sister site reuses that session. Authorization is an explicit `REUNION_ADMIN_USERS` allowlist evaluated against the canonical SSO subject or the optional `mappings["reunion"]` value.

All mutating endpoints also require a same-origin CSRF token. Admin responses are marked `no-store`.

## Visual publishing

The editor uses the live public itinerary as a same-origin iframe, adds temporary `contenteditable` controls, and submits only the `<main>` content. The server rejects scripts, embedded frames, unsafe event handlers, unsafe URL schemes, and incorrect reunion branding. RSVP controls live on the separate static RSVP page and are not part of itinerary publishing.

Publishing requires a clean dedicated `master` checkout. A private backup is written outside Git, then `deploy/publish.sh` commits the change directly to `master`, pushes it, and redeploys the static document root. If publishing fails before Git creates a commit, the old page is restored automatically.

## Codex boundary

Browser text is never executed as a command. The service invokes one fixed executable from `REUNION_CODEX_RUNNER`, passes the user message over standard input, and provides fixed environment paths for the repository and durable session directory. The host-specific runner is responsible for using the installed Codex CLI/SDK or the existing `webapps/codex_apps` session machinery.
