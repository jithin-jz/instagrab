# Docker Setup

1. Copy the environment template and fill every required value:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Build the image:

   ```bash
   docker compose build
   ```

3. Start the service:

   ```bash
   docker compose up -d
   ```

4. View logs:

   ```bash
   docker compose logs -f ig-tg-bot
   ```

5. Check health:

   ```bash
   curl http://localhost:8000/health
   ```

6. Stop the service:

   ```bash
   docker compose down
   ```

The SQLite database is stored in the named Docker volume `ig_tg_data` at `/data/ig_tg_bot.db` inside the container.

To reset all persisted app data:

```bash
docker compose down -v
```

Use your public HTTPS domain or ngrok URL as `BASE_URL`, then register this webhook callback with Meta:

```text
https://your-public-domain.com/webhook
```
