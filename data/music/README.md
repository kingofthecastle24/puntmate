# PuntMate Story music

Music for Instagram Story videos comes ONLY from this folder, and only after
its license is verified for the account/use (Micah's music grant 2026-11-06:
suitable cleared music, no spend; previewed and accepted on the 27.5s proof).

## Rules
1. Use a track from `tracks.json` via `scripts/render_story_video.py --track <id>`.
2. Meta Sound Collection tracks are licensed for Meta Company Products ONLY.
   A rendered video with music must go to Instagram (Story) and nowhere else -
   never Telegram, never other platforms. Static images stay the default there.
3. License terms: https://www.facebook.com/sound/collection/terms (verified
   2026-11-06). No automated-interruption guarantee exists for any source;
   Sound Collection is Meta's own licensed library, the strongest no-spend
   coverage available.
4. Adding a new track: download from Sound Collection while logged in,
   verify the terms still cover the use, add the file + a `tracks.json` entry
   with license_url and license_checked.

## Story video spec (Meta media endpoint reference)
3-60s, 9:16, H.264/HEVC 23-60fps, AAC ~128kbps. render_story_video.py outputs
1080x1920 H.264 + AAC 128k, 30fps, no zoom on frames, ~9s dwell per frame.
