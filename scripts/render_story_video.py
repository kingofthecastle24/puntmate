"""
render_story_video.py — Build an Instagram Story video (with licensed music)
from a PuntMate review package's static Story frames.

Why this exists:
  Micah (2026-11-06, WhatsApp) authorized adding suitable, cleared music to
  PuntMate Stories ("music related to the page ... surprise me", no spend).
  Static image Stories remain the default and the fallback; this renderer is
  opt-in via --video on the Story publish paths.

Rules baked in (learned 2026-11-06 proof review):
  - NO zoom/pan on the dense branded cards — zoom crops the footer/18+ line.
    Frames render pixel-static for the full dwell.
  - ~9s dwell per frame + 0.5s crossfades (readable on 7-leg cards).
  - Output spec per Meta's media endpoint reference (Story video containers):
    3-60s duration, 9:16, H.264 video 23-60fps, AAC audio ~128kbps.
    https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media
  - Audio MUST come from the Meta Sound Collection registry in
    data/music/tracks.json. SC audio is licensed for Meta products ONLY —
    the rendered video must never be published to Telegram or other
    non-Meta surfaces. See data/music/README.md.

Usage:
  python3 scripts/render_story_video.py \
      --frames data/review/<pkg>/story.png data/review/<pkg>/story-2.png data/review/<pkg>/story-breakdown.png \
      --track energy_instrumental \
      --out data/review/<pkg>/story-video.mp4

Requires ffmpeg + ffprobe on PATH.
"""

import argparse
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS_PATH = os.path.join(REPO_ROOT, "data", "music", "tracks.json")

# Video constants (Meta Story spec, see module docstring)
WIDTH, HEIGHT = 1080, 1920
FPS = 30
DWELL = 9.0          # seconds each frame is fully on screen
XFADE = 0.5          # crossfade duration between frames
AUDIO_BITRATE = "128k"
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"  # platform-standard loudness


def load_track(track_id):
    if not os.path.exists(TRACKS_PATH):
        sys.exit(f"Music registry not found: {TRACKS_PATH}")
    with open(TRACKS_PATH) as f:
        registry = json.load(f)
    track = registry.get("tracks", {}).get(track_id)
    if not track:
        sys.exit(f"Track '{track_id}' not in {TRACKS_PATH} — only registry "
                 f"tracks (Meta Sound Collection, license-verified) may be used.")
    local = os.path.join(REPO_ROOT, track["file"])
    if not os.path.exists(local):
        sys.exit(f"Track file missing: {local} — download per data/music/README.md.")
    return track, local


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", nargs="+", required=True, help="Story frame PNGs in order (2+)")
    ap.add_argument("--track", required=True, help="Track id from data/music/tracks.json")
    ap.add_argument("--out", required=True, help="Output .mp4 path")
    ap.add_argument("--audio-start", type=float, default=None,
                    help="Seconds into the track to start (default: registry value)")
    ap.add_argument("--dwell", type=float, default=DWELL)
    ap.add_argument("--xfade", type=float, default=XFADE)
    args = ap.parse_args()

    frames = args.frames
    for fr in frames:
        if not os.path.exists(fr):
            sys.exit(f"Frame not found: {fr}")
    if len(frames) < 2:
        sys.exit("Need at least 2 frames for a Story video.")

    track, audio_path = load_track(args.track)
    audio_start = args.audio_start if args.audio_start is not None else track.get("audio_start", 0.0)

    n = len(frames)
    seg = args.dwell + args.xfade          # per-frame loop length; xfade overlaps into next
    duration = n * args.dwell + (n - 1) * args.xfade  # total output length
    if duration > 60:
        sys.exit(f"Total duration {duration:.1f}s exceeds the 60s Story limit; reduce dwell/frames.")

    # Build ffmpeg command: loop each frame, scale/pad to 1080x1920, xfade chain,
    # trimmed audio with fades + loudnorm.
    cmd = ["ffmpeg", "-y"]
    for fr in frames:
        cmd += ["-loop", "1", "-t", f"{seg:.3f}", "-i", fr]
    cmd += ["-ss", f"{audio_start:.3f}", "-t", f"{duration:.3f}", "-i", audio_path]

    vfilters = []
    for i in range(n):
        vfilters.append(
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS}[v{i}]"
        )
    # chained crossfades: offsets accumulate dwell per frame
    prev = "v0"
    for i in range(1, n):
        offset = i * args.dwell + (i - 1) * args.xfade  # wait, see note below
        # offset = when the transition starts = i*dwell + (i-1)*xfade? No:
        # each xfade starts at previous chain length - xfade.
        # Chain length after k xfades = (k+1)*seg - k*xfade.
        # Transition k (0-indexed k-1) starts at chain_length_before - xfade.
        chain_len = i * seg - (i - 1) * args.xfade
        offset = chain_len - args.xfade
        out = f"vx{i}" if i < n - 1 else "vout"
        vfilters.append(f"[{prev}][v{i}]xfade=transition=fade:duration={args.xfade}:offset={offset:.3f}[{out}]")
        prev = out

    afade_in_end = 1.0
    afade_out_start = max(duration - 1.5, 0)
    afilter = (
        f"[{n}:a]{LOUDNORM},afade=t=in:st=0:d={afade_in_end},"
        f"afade=t=out:st={afade_out_start:.3f}:d=1.5[aout]"
    )

    filtergraph = ";".join(vfilters + [afilter])
    cmd += [
        "-filter_complex", filtergraph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000",
        "-movflags", "+faststart",
        "-t", f"{duration:.3f}",
        args.out,
    ]
    print("Running:", " ".join(cmd[:6]), "...")
    subprocess.run(cmd, check=True)

    # Verify output duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", args.out],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"✅ Story video rendered: {args.out} ({float(probe):.1f}s, "
          f"track '{track['title']}' by {track['artist']}, audio from {audio_start:.0f}s)")
    print("   Reminder: Meta Sound Collection license covers Meta products ONLY — "
          "do not publish this video to Telegram or other non-Meta surfaces.")


if __name__ == "__main__":
    main()
