# Local Setup Guide

1. Open a terminal in this folder:

   ```bash
   cd ig-tg-bot
   ```

2. Create and activate a Python virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   On Windows PowerShell:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill every value:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Run the FastAPI server:

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. Install ngrok from `https://ngrok.com/download`, then expose the local server:

   ```bash
   ngrok http 8000
   ```

7. Copy the HTTPS ngrok URL, set `BASE_URL` in `.env` to that URL, and use this callback URL in Meta:

   ```text
   https://your-ngrok-domain.ngrok-free.app/webhook
   ```

For Docker-based setup, use `DOCKER_SETUP.md` instead of the virtualenv steps above.
