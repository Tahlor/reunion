# Hazard Family Reunion 2026

Static itinerary and meal-RSVP landing page for the Hazard family reunion, August 1–8, 2026.

## Files

- `index.html` — complete mobile-friendly itinerary, maps, safety notes, and RSVP fallback builder.
- `config.js` — public runtime configuration. Add the published Google Form URL here after creating the form.
- `create_hazard_rsvp_form.gs` — one-run Google Apps Script that creates the household meal RSVP form, response spreadsheet, and live per-meal headcounts.
- `deploy/` — Archimedes deployment helper and Nginx location example.

## Create the meal RSVP form

1. Open `https://script.new` in the Google account that should own the responses.
2. Paste `create_hazard_rsvp_form.gs` into the editor.
3. Run `createHazardMealRsvp` and authorize Forms and Sheets access.
4. Copy the logged `window.REUNION_CONFIG = ...` line into `config.js`.
5. Commit the updated `config.js` and redeploy. The form URL is public and is not a secret.

## Local preview

```bash
python3 -m http.server 8080
# Open http://localhost:8080/
```

## Production target

`https://taylorarchibald.com/reunion/` on Archimedes. See the open deployment issue and `deploy/nginx-location.conf.example`.
