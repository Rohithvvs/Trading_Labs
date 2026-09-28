# Telegram Community Setup & Configuration Guide

This guide describes how to configure the dedicated Telegram Channel and linked Discussion Group for Trading Labs Public Beta, as well as how to enable real-time bug/feedback forwarding via the Telegram Bot.

---

## 1. Official Beta Channels & Groups

Trading Labs operates two linked Telegram spaces for the public beta:

1. **Official Announcement Channel**
   - **Purpose:** Release announcements, maintenance windows, beta updates, feature drops.
   - **Default Link:** `https://t.me/TradingLabsOfficial` (Configurable via `TELEGRAM_CHANNEL_URL` or `VITE_TELEGRAM_CHANNEL_URL`)

2. **Linked Discussion Group**
   - **Purpose:** Community support, bug reports, feature discussions, and trader feedback.
   - **Default Link:** `https://t.me/TradingLabsDiscussion` (Configurable via `TELEGRAM_GROUP_URL` or `VITE_TELEGRAM_GROUP_URL`)

---

## 2. Linking the Group to the Channel in Telegram

1. Open Telegram and create a new **Channel** (e.g., `Trading Labs | Beta Announcements`).
2. Go to **Channel Settings** > **Discussion** > **Link a Group**.
3. Create or select your discussion group (e.g., `Trading Labs | Community Discussion`).
4. Whenever announcements are posted to the channel, comments and discussion threads automatically appear in the linked discussion group.

---

## 3. Automated Telegram Bot for Bug & Feedback Forwarding

The backend includes a native Telegram notification dispatcher (`app/services/telegram_service.py`). When a user submits feedback or reports a bug in the application, the system can automatically post an alert directly to your Telegram team chat or discussion group.

### Setup Steps:
1. Open Telegram and message `@BotFather`.
2. Send `/newbot`, name it (e.g. `TradingLabsBetaBot`), and save the bot token.
3. Add the bot to your private team admin chat or discussion group as an Administrator.
4. Retrieve the chat ID (using `@userinfobot` or `https://api.telegram.org/bot<TOKEN>/getUpdates`).
5. Configure the environment variables in your `.env` (or Render / deployment environment):

```env
TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
TELEGRAM_CHAT_ID="-1001234567890"

# Optional community link overrides
TELEGRAM_CHANNEL_URL="https://t.me/YourCustomChannel"
TELEGRAM_GROUP_URL="https://t.me/YourCustomGroup"
```

If these environment variables are not set, the feedback system safely logs the feedback locally to `logs/feedback.jsonl` without errors.
