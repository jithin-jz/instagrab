# Telegram Setup

1. Message `@BotFather` in Telegram.

2. Run `/newbot`, choose a name and username, then copy the token.

3. Set the token in `.env`:

   ```text
   TG_BOT_TOKEN=your_bot_token_here
   ```

4. Get your personal Telegram chat ID:

   - Send any message to your new bot.
   - Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`.
   - Find the JSON object with `"chat":{"id": YOUR_ID}`.

5. Set the admin chat ID in `.env`:

   ```text
   ADMIN_TELEGRAM_ID=123456789
   ```

6. Optional: run a local Bot API server for up to 2GB file support:

   ```bash
   docker run -d -p 8081:8081 \
     -e TELEGRAM_API_ID=your_api_id \
     -e TELEGRAM_API_HASH=your_api_hash \
     aiogram/telegram-bot-api:latest
   ```

7. If using the local server, set:

   ```text
   TG_LOCAL_SERVER_URL=http://localhost:8081
   ```

8. Start the Python service and send `/start` to the bot to link your Instagram username.
