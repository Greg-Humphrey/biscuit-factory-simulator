# Biscuit Factory Simulator

## Project Overview
Educational operations management simulator for A-Level business students. Students design and run a virtual biscuit factory, making strategic decisions about factory layout, production planning, and financial management. Supports multi-team classroom competitions with real-time scenario events and comprehensive financial reporting.

## Key Commands
- Run locally: `uvicorn api:app --reload`
- Run with Docker: `docker build -t biscuit . && docker run -p 8000:8000 biscuit`
- Deploy: push to GitHub main branch (Railway deploys automatically via GitHub integration)

## Deployment
- Hosted on Railway, deployed automatically from GitHub
- Production: main branch → simprentice.com (marketing) + sim.simprentice.com redirects to /app
- Staging/dev: dev branch → Railway dev service (separate URL)
- Both environments have Railway persistent volumes mounted at /data
- SQLite database stored at /data/simulator.db (set via DB_PATH env var)
- SECRET_KEY for JWT is hardcoded in auth.py (not an env var — this is intentional for now)
- NO_CACHE=1 is a shared env var on both Railway services

## Architecture Summary
- FastAPI backend (api.py is the main entry point)
- SQLite via database.py
- Jinja2 HTML templates in templates/
- Static assets in static/
- PDF reports generated via WeasyPrint (pdf_engine.py)
- Teams progress through setup → operating phases; factory locked after setup
- Teacher controls global month advancement for all teams

## Routing
- / → always serves marketing homepage (templates/marketing/homepage.html)
- /app → simulator entry point (templates/home.html)
- sim.simprentice.com redirects to simprentice.com/app
- All internal redirects and the Home nav link point to /app, not /

## Multi-Device Compatibility (Long-Term Goal)
Greg wants the app to be fully compatible across phone, tablet, laptop, and large displays.
This is a future goal — not being built now — but every new UI component should be written
with responsiveness in mind to avoid large rework later. Specifically:
- Always add `<meta name="viewport" content="width=device-width, initial-scale=1">` to new pages
- Prefer CSS flexbox or grid over fixed-width layouts
- Avoid hardcoded pixel widths on containers — use percentages or max-width
- Tables are the hardest problem on mobile; when building new tables consider whether
  the data could work as cards or stacked rows on small screens
- The factory setup builder and wide teacher dashboard tables are known problem areas
  that will need dedicated mobile work when the time comes
- Do not retrofit existing pages unprompted — only apply responsive patterns to new work

## Future Platform Vision
Simprentice is planned to become a multi-product SaaS platform:
- Teachers self-register and get isolated accounts with their own simulator instances
- Students access teacher sessions without logging in (as teams, same as today)
- Each teacher's data is fully isolated from other teachers
- Additional simulators beyond the Biscuit Factory will be separate apps sharing a login
- This is a future project — do not pre-build it, but avoid architectural decisions
  that would make it harder to introduce later

## Page & Route Terminology

| Screen | URL | Who sees it |
|---|---|---|
| Marketing homepage | `/` | Everyone (unauthenticated) |
| Student entry | `/student` | Students entering a class code |
| Session landing | `/join/<code>` | Students after entering code |
| Simulator Hub | `/hub` | Teachers after login — shows simulator tiles |
| Teacher Dashboard | `/teacher-dashboard` | Teachers inside a Biscuit Factory session |
| Team Dashboard | `/team-dashboard` | Students inside a session |

- **Simulator Hub** — platform-level landing for teachers. Shows one tile per available simulator. Currently only Biscuit Factory. Future sims add more tiles here.
- **Teacher Dashboard** — simulator-specific classroom view. Manages teams, advances months, edits scenarios. Belongs to the Biscuit Factory simulator only.
- **Session** — one run of a simulator with a class. Has a name, join code, month count, and status (setup / active / finished).
- Teacher login → `/hub`. All within-simulator redirects stay on `/teacher-dashboard`.

## Licensing & School Admin (Current Approach)
- Licences are stored in the database (school and teacher level)
- Greg manually manages school/teacher accounts in the near term — no self-service admin UI needed yet
- Self-service school registration is the long-term vision but not being built now
- Automatic licence management (renewals, provisioning) is a future scaling concern — ignore for now
- Licence data should be added to the DB schema so the foundation is there without over-engineering the workflows

## Giving Greg Instructions
- Greg is a novice coder with limited computer science knowledge
- Always explain commands in plain English before giving them
- Offer options where relevant so Greg can make an informed choice
- Avoid jargon without explanation
