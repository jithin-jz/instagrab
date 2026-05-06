# Setup Guide

This guide covers setting up Instagrab (Instagram-Telegram bot) using Docker.

## Prerequisites

- Docker and Docker Compose installed
- Telegram account
- Instagram Business or Creator account
- Meta Developer account

## Step 1: Meta Developer App Setup

1. Go to [https://developers.facebook.com/apps](https://developers.facebook.com/apps) and create a Meta app.

2. In the app dashboard, add the Instagram Graph API product.

3. Link the Facebook Page that owns your Instagram Business account:
   - Open Facebook Page settings
   - Connect the Instagram account
   - Confirm the Instagram account is a Business or Creator account

4. Generate a long-lived Instagram access token with these permissions:
   ```
   instagram_basic
   instagram_manage_comments
   pages_read_engagement
   ```
   Use Graph API Explorer or your app's OAuth flow. Exchange the short-lived token for a long-lived token before placing it in `.env`.

5. Get your Instagram Business Account ID:
   ```http
   GET https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN
   GET https://graph.facebook.com/v19.0/{page-id}?fields=instagram_business_account&access_token=YOUR_TOKEN
   ```
   Use the returned `instagram_business_account.id` value as `IG_BUSINESS_ID`.

6. Register the webhook in the Meta app dashboard:
   - Callback URL: `https://your-public-domain.com/webhook`
   - Verify token: the same value as `IG_VERIFY_TOKEN`
   - Subscribe to the `mentions` field for Instagram

7. Complete App Review if Meta requires it for production access to the permissions or webhook fields.

## Step 2: Telegram Bot Setup

1. Message `@BotFather` in Telegram.

2. Run `/newbot`, choose a name and username, then copy the token.

3. Get your personal Telegram chat ID:
   - Send any message to your new bot
   - Visit `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - Find the JSON object with `"chat":{"id": YOUR_ID}`

4. Optional: run a local Bot API server for up to 2GB file support:
   ```bash
   docker run -d -p 8081:8081 \
     -e TELEGRAM_API_ID=your_api_id \
     -e TELEGRAM_API_HASH=your_api_hash \
     aiogram/telegram-bot-api:latest
   ```

## Step 3: Environment Configuration

Copy `.env.example` to `.env` and fill every required value:

```bash
cp .env.example .env
```

On Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

Required environment variables:
- `IG_APP_ID`: Meta App ID
- `IG_APP_SECRET`: Meta App Secret
- `IG_VERIFY_TOKEN`: Webhook verify token (choose any string)
- `IG_ACCESS_TOKEN`: Long-lived Instagram access token
- `IG_BUSINESS_ID`: Instagram Business Account ID
- `TG_BOT_TOKEN`: Telegram bot token from @BotFather
- `ADMIN_TELEGRAM_ID`: Your Telegram chat ID
- `BASE_URL`: Your public HTTPS domain or ngrok URL
- `TG_LOCAL_SERVER_URL`: Optional, local Bot API server URL (e.g., `http://localhost:8081`)
- `TG_WEBHOOK_SECRET`: Optional, secret for Telegram webhook signature verification
- `TG_POLLING`: Set to `true` to use polling instead of webhook for Telegram
- `MAX_CONCURRENT_DOWNLOADS`: Max concurrent media downloads (default: 3)
- `RATE_LIMIT_SECONDS`: Rate limit window in seconds (default: 60)

## Step 4: Docker Setup

### Production

1. Build and start the production service:
   ```bash
   docker compose up -d
   ```

2. View logs:
   ```bash
   docker compose logs -f instagrab
   ```

3. Check health:
   ```bash
   curl http://localhost:8000/health
   ```

4. Stop the service:
   ```bash
   docker compose down
   ```

The SQLite database is stored in the named Docker volume `instagrab_data` at `/data/instagrab.db` inside the container.

To reset all persisted app data:
```bash
docker compose down -v
```

### Development

For development with hot reload:
```bash
docker compose --profile dev up
```

This mounts the current directory for live code reloading.

### Testing

To run the test suite:
```bash
docker compose --profile test run --rm ig-tg-bot-test
```

## Step 5: Testing Webhook

Use this payload to simulate an Instagram mention webhook:
```json
{"object":"instagram","entry":[{"id":"17841400000000000","time":1715792400,"changes":[{"field":"mentions","value":{"media_id":"17912345678901234","comment_id":"18012345678901234","from":{"id":"17890000000000000","username":"johndoe"},"text":"@TargetAccount"}}]}]}
```

Compute a valid HMAC signature with your `IG_APP_SECRET`:
```bash
BODY='{"object":"instagram","entry":[{"id":"17841400000000000","time":1715792400,"changes":[{"field":"mentions","value":{"media_id":"17912345678901234","comment_id":"18012345678901234","from":{"id":"17890000000000000","username":"johndoe"},"text":"@TargetAccount"}}]}]}'
SECRET='your_meta_app_secret'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -binary | xxd -p -c 256)
```

Send the webhook:
```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -H "X-Hub-Signature-256: sha256=$SIG" --data "$BODY"
```

## Step 6: Telegram Bot Registration

1. Start the Docker service
2. Send `/start` to your Telegram bot to link your Instagram username
3. Use `/me` to verify your linked Instagram account
4. As admin, use `/stats`, `/logs`, and `/users` to monitor the bot

## Pre-Launch Checklist

- [ ] Instagram account is a Business or Creator account
- [ ] Instagram account is linked to the correct Facebook Page
- [ ] Meta app has Instagram Graph API enabled
- [ ] Meta app has `instagram_basic`, `instagram_manage_comments`, and `pages_read_engagement` permissions
- [ ] Meta app webhook callback URL points to `https://your-domain.com/webhook`
- [ ] Meta webhook verify token exactly matches `IG_VERIFY_TOKEN`
- [ ] Meta webhook is subscribed to Instagram `mentions`
- [ ] App Review is complete if required for production use
- [ ] `IG_APP_ID` is set in `.env`
- [ ] `IG_APP_SECRET` is set in `.env`
- [ ] `IG_ACCESS_TOKEN` is a long-lived token
- [ ] `IG_BUSINESS_ID` is the Instagram Business Account ID, not the Page ID
- [ ] Telegram bot token from `@BotFather` is set as `TG_BOT_TOKEN`
- [ ] Admin Telegram chat ID is set as `ADMIN_TELEGRAM_ID`
- [ ] Local Bot API server is running if `TG_LOCAL_SERVER_URL=http://localhost:8081`
- [ ] Docker Compose builds without errors
- [ ] `docker compose up -d` starts the service
- [ ] `/health` returns `status: running`
- [ ] Startup follower sync completes successfully
- [ ] Telegram `/start` registration flow saves a user
- [ ] Telegram `/me` shows the linked Instagram account
- [ ] Admin `/stats`, `/logs`, and `/users` work only for `ADMIN_TELEGRAM_ID`
- [ ] A test webhook with a valid HMAC returns `{"status":"ok"}`
- [ ] Invalid webhook HMACs are rejected with HTTP 401
- [ ] Duplicate media IDs are skipped
- [ ] Non-followers are marked as `not_follower`
- [ ] Followers without Telegram registration are marked as `not_registered`
- [ ] Rate limit warning appears when one user requests twice within 60 seconds
- [ ] Direct CDN download works for a readable media URL
- [ ] yt-dlp fallback works for an Instagram permalink
- [ ] Oversized files send a Telegram warning instead of crashing
- [ ] Successful deliveries increment `total_delivered`
- [ ] Logs appear in console and in the `logs` table
- [ ] Scheduled follower sync, token health check, token refresh, and cleanup jobs are registered
- [ ] Database persists in Docker volume `instagrab_data`
- [ ] HTTPS endpoint is reachable from Meta's webhook servers
