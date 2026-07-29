# Reunion site agent instructions

This repository is the **Hazard Family Reunion** site. Do not rename it to an Archibald, Casey-and-Morgan, or other reunion.

## Production behavior

- Public URL: `https://taylorarchibald.com/reunion/`
- Admin chat: `/reunion/admin`
- Visual editor: `/reunion/edit`
- Production host: Archimedes, behind the existing Nginx server and webapps Universal SSO.
- The public page remains static; only `/admin`, `/edit`, and `/api/` are proxied to the local reunion admin service.

## Change policy

- Work only in this repository.
- Preserve the existing itinerary, RSVP controls, and Hazard branding unless the user explicitly requests a change.
- Finish requested changes by validating them, committing directly to `master`, pushing `origin/master`, and running `deploy/deploy.sh` on Archimedes.
- Do not leave feature branches behind.
- Do not expose SSO secrets, Codex credentials, SSH keys, Google Form response data, or private audit data in Git or the public document root.
