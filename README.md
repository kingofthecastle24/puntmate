# PuntMate NZ 🎯

Automated sports picks for NZ audiences — NRL, FIFA World Cup, Super Rugby, NBA.

Posts daily picks to Telegram automatically via GitHub Actions.

## Setup

### 1. Get API keys

| Key | Where | Cost |
|-----|-------|------|
| `ANTHROPIC_API_KEY` | platform.anthropic.com | ~$0.10/month |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | Free |
| `TELEGRAM_CHANNEL_ID` | See below | Free |
| `ODDS_API_KEY` | the-odds-api.com | Free (500 req/month) |

### 2. Get your Telegram Channel ID

1. Add your bot as admin to your channel
2. Send a test message to the channel
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the `chat.id` value — it will be negative (e.g. `-1001234567890`)

### 3. Add secrets to GitHub

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

Add all four keys listed above.

### 4. Enable GitHub Actions

Push this repo to GitHub. Actions will run automatically on schedule.

To test immediately: go to Actions tab → "PuntMate Daily Picks" → Run workflow.

## Schedule

- 8am NZT daily (main run)
- 6pm NZT Friday/Saturday/Sunday (weekend evening games)

## Stack

- **Odds**: The Odds API (free tier) — covers World Cup, NRL, NBA, Super Rugby
- **Picks**: Claude Haiku API
- **Posting**: Telegram Bot API
- **Runner**: GitHub Actions (free)
