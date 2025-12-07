# DormDeck AI — Campus Concierge (MVP)

**Team:** Campus Rewind  
**Course:** CS391 — Complex Computing Problem

## What it is
DormDeck AI is a chat-first campus concierge that finds sellers on campus by reasoning about **time**, **location**, and **intent**, and connects students instantly via WhatsApp.

## Run locally
1. `git clone <repo>`
2. Create `.env` with `GEMINI_API_KEY_DORMDECK=your_key`
3. `python -m venv .venv && source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `streamlit run app.py`

## Files
- `app.py` — Streamlit front-end
- `dormdeck_engine.py` — Recommendation engine, LLM integration
- `services.json` — Seller database (JSON)
- `tests/` — pytest tests

## Day 3 work (what changed)
- Robust time handling (midnight / 24/7)
- LLM cache to reduce calls
- Seller onboarding form (no login)
- Testing + README + deployment instructions

## Deploying to Streamlit Cloud
1. Push repo to GitHub.
2. On Streamlit Community Cloud, create new app pointing to your repo and branch.
3. Set environment variable `GEMINI_API_KEY_DORMDECK`.
4. Deploy and verify.

## Demo script (1 minute)
See `DEMO.md` or use the one-page script below.

