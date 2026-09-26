# vpnpromo: daily TikTok videos and memes for a VPN

Every day the script:

1. **Writes scripts.** Claude writes 2-5 new ideas in formats like meme, POV, story and "top 3", using only the facts you list about your product. Past ideas go into `state/history.json` so topics don't repeat.
2. **Renders videos.** Output is vertical 1080×1920 mp4 with large text slides, a Russian voice-over (edge-tts), a background (your clips from `assets/backgrounds` or a gradient) and music from `assets/music`.
3. **Publishes.**
   - **Telegram** (default): each video comes to you in a chat with its caption and hashtags ready to copy. You post it to TikTok from your phone in about 30 seconds.
   - **TikTok API** (optional): direct post through the official Content Posting API.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml          # fill in brand.features etc.
export ANTHROPIC_API_KEY=...
export TELEGRAM_BOT_TOKEN=...               # from @BotFather
export TELEGRAM_CHAT_ID=...                 # your id, e.g. from @userinfobot

python -m vpnpromo --demo --dry-run         # test render, no API calls
python -m vpnpromo --dry-run                # real scripts, no publishing (files go to output/)
python -m vpnpromo                          # full run
```

## Running every day

`.github/workflows/daily.yml` runs every day at 16:47 MSK. In the repo, go to Settings → Secrets → Actions and add:
`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `CONFIG_YAML` (the full contents of your config.yaml).
You can also use cron on a VPS: `47 16 * * * cd /path && python -m vpnpromo`.

## Making the videos look better

- `assets/backgrounds/`: put vertical or horizontal clips here (gameplay, satisfying videos, your own screen recordings). The script picks one at random and crops it to 9:16. Only use footage you have the rights to (your own or royalty-free, e.g. Pexels).
- `assets/music/`: background tracks. Trending TikTok sounds are better added by hand in the app when you post.
- `assets/fonts/`: a bold Cyrillic font, e.g. Montserrat ExtraBold (Google Fonts, free).

## TikTok direct post

1. Register an app at developers.tiktok.com, add Login Kit and Content Posting API (Direct Post), and get the `video.publish` scope.
2. Complete OAuth for your account and add the secrets `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` and `TIKTOK_REFRESH_TOKEN`.
3. Set `publish.tiktok: true` in the config. Until TikTok audits your app, posts are only visible to you (`SELF_ONLY`).
