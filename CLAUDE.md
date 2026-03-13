# Biscuit Factory Simulator

## Project Overview
Educational operations management simulator for A-Level business students. Students design and run a virtual biscuit factory, making strategic decisions about factory layout, production planning, and financial management. Supports multi-team classroom competitions with real-time scenario events and comprehensive financial reporting.

## Key Commands
- Run locally: `uvicorn api:app --reload`
- Run with Docker: `docker build -t biscuit . && docker run -p 8000:8000 biscuit`
- Deploy: push to GitHub main branch (Railway deploys automatically via GitHub integration)

## Deployment
- Hosted on Railway, deployed automatically from GitHub (main branch)
- Live domain: https://sim.simprentice.com/
- SQLite database (simulator.db) — note: Railway volumes may reset on redeploy, so treat the DB as ephemeral unless a persistent volume is configured
- Environment variables: JWT_SECRET

## Architecture Summary
- FastAPI backend (api.py is the main entry point)
- SQLite via database.py
- Jinja2 HTML templates in templates/
- Static assets in static/
- PDF reports generated via WeasyPrint (pdf_engine.py)
- Teams progress through setup → operating phases; factory locked after setup
- Teacher controls global month advancement for all teams

## Giving Greg Instructions
- Greg is a novice coder with limited computer science knowledge
- Always explain commands in plain English before giving them
- Offer options where relevant so Greg can make an informed choice
- Avoid jargon without explanation
