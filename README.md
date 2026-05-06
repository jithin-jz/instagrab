# Instagrab

Instagram → Telegram Delivery Bot

A FastAPI application that receives Instagram mention webhooks, downloads tagged media, and forwards it privately to registered Telegram users.

## Features

- **Instagram Webhook Integration**: Receives mention webhooks from Instagram Graph API
- **Media Download**: Downloads Instagram media using yt-dlp with CDN fallback
- **Telegram Delivery**: Forwards media to registered users via Telegram bot
- **User Management**: Users can register via Telegram bot by linking their Instagram username
- **Follower Verification**: Only delivers media from followers to prevent spam
- **Rate Limiting**: Prevents abuse with configurable rate limits
- **Admin Commands**: Stats, logs, and user management for admins
- **Scheduled Tasks**: Automatic follower sync, token health checks, and cleanup

## Tech Stack

- **FastAPI**: Web framework
- **python-telegram-bot**: Telegram bot API
- **yt-dlp**: Media downloader
- **APScheduler**: Task scheduling
- **SQLite**: Database (persisted in Docker volume)
- **Docker**: Containerization

## Prerequisites

- Docker and Docker Compose
- Telegram account
- Instagram Business or Creator account
- Meta Developer account

## Quick Start

1. Clone the repository
2. Copy `.env.example` to `.env` and configure environment variables
3. Run `docker compose up -d`
4. Send `/start` to your Telegram bot to register

## Setup

For detailed setup instructions, see [docs/setup.md](docs/setup.md)

### Environment Variables

Required variables in `.env`:
- `IG_APP_ID`: Meta App ID
- `IG_APP_SECRET`: Meta App Secret
- `IG_VERIFY_TOKEN`: Webhook verify token
- `IG_ACCESS_TOKEN`: Long-lived Instagram access token
- `IG_BUSINESS_ID`: Instagram Business Account ID
- `TG_BOT_TOKEN`: Telegram bot token from @BotFather
- `ADMIN_TELEGRAM_ID`: Your Telegram chat ID
- `BASE_URL`: Your public HTTPS domain or ngrok URL

Optional variables:
- `TG_LOCAL_SERVER_URL`: Local Bot API server URL for large file support
- `TG_WEBHOOK_SECRET`: Secret for Telegram webhook verification
- `TG_POLLING`: Set to `true` to use polling instead of webhook
- `MAX_CONCURRENT_DOWNLOADS`: Max concurrent media downloads (default: 3)
- `RATE_LIMIT_SECONDS`: Rate limit window in seconds (default: 60)

## Docker Commands

### Production
```bash
docker compose up -d
docker compose logs -f instagrab
docker compose down
```

### Development (with hot reload)
```bash
docker compose --profile dev up
```

### Testing
```bash
docker compose --profile test run --rm ig-tg-bot-test
```

## Telegram Bot Commands

- `/start` - Register your Instagram username
- `/me` - View your linked Instagram account
- `/stats` - View delivery statistics (admin only)
- `/logs` - View recent logs (admin only)
- `/users` - View registered users (admin only)

## API Endpoints

- `GET /health` - Health check endpoint
- `POST /webhook` - Instagram webhook endpoint
- `POST /telegram` - Telegram webhook endpoint

## Documentation

- [Docker Setup](docs/DOCKER_SETUP.md)
- [Local Setup](docs/LOCAL_SETUP.md)
- [Meta Developer App Setup](docs/META_DEVELOPER_APP_SETUP.md)
- [Telegram Setup](docs/TELEGRAM_SETUP.md)
- [Pre-Launch Checklist](docs/PRE_LAUNCH_CHECKLIST.md)
- [Testing Webhooks](docs/TEST_WEBHOOK.md)

## License

MIT License
