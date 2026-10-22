# YouTube Automation V3 — Independent Build from Zero

A reproducible, modular, mostly-automated educational-video production system.
Content niche: how machines and technology work — engineering, science,
mechanisms, inventions, and useful technical explanations.

The first deliverable is a complete sample video: **How a Four-Stroke Engine Works**.

## Status

Implemented stages:
- Topic planner (A)
- Research & fact-checking engine (B)
- Scriptwriter (C)
- Narration & subtitles via eSpeak NG TTS (D)
- 2D animation engine using Pillow (E)
- Thumbnail engine (F)
- Video assembler via FFmpeg (G)
- Quality checker (H)
- YouTube publishing — dry-run only, awaiting credentials & approval (I)
- Scheduler & monitoring config (J)

All stages are callable Python modules with bounded retries, intermediate
caching, and automated tests.

## Environment verified

- Python 3.14.8
- Pillow 12.2.0, NumPy 2.4.6
- FFmpeg 8.1.2 / ffprobe
- eSpeak NG 1.52.0 (TTS)
- pytest 9.0.3
- Alpine Linux (apk), network available

## Cost & resource constraints (honored)

- No mandatory paid AI APIs, no subscriptions, no payment-card verification.
- No local language-model download on phone.
- Free / open-source tools wherever practical.
- Deterministic local tools for rendering, subtitles, validation, assembly.

## Project layout

```
YouTube-Automation-Project-B/
├── config.yaml            # runtime config (no secrets)
├── config.example.yaml    # example config without secrets
├── scheduler.yaml         # unattended cloud schedule config
├── requirements.txt       # Python deps
├── README.md              # this file
├── src/                   # application modules
│   ├── __init__.py
│   ├── pipeline.py        # end-to-end orchestrator
│   ├── topic_planner.py
│   ├── research.py
│   ├── scriptwriter.py
│   ├── narration.py       # TTS + SRT subtitles
│   ├── animation.py       # Pillow 2D animation
│   ├── thumbnail.py
│   ├── assembler.py       # FFmpeg assembly + validation
│   ├── quality.py         # quality checker + report
│   ├── publisher.py       # YouTube dry-run publishing
│   ├── scheduler.py       # scheduler + status report
│   └── manifest.py        # output manifest
├── tests/                 # unit + integration tests
├── .github/workflows/     # cloud CI / scheduler workflows
├── data/                  # topic registry
├── output/                # rendered outputs (sample video here)
└── samples/               # sample manifests / configs
```

## Local execution

```bash
# install system deps (Alpine example)
apk add --no-cache ffmpeg espeak-ng py3-pytest py3-numpy py3-pip

# Python deps
python3 -m pip install -r requirements.txt   # or use apk py3- packages

# run the full four-stroke-engine sample pipeline
python3 -m src.pipeline --topic four_stroke_engine --run-all --manual

# run tests
pytest

# status / dry-run
python3 -m src.scheduler status
python3 -c "from src.publisher import YouTubePublisher; print(YouTubePublisher().dry_run('four_stroke_engine','How a Four-Stroke Engine Works','output/video/four_stroke_engine_final.mp4'))"
```

## Cloud execution

Target: one video every two days via a configurable cron scheduler.
`scheduler.yaml` defines the schedule, retry limits, resume behavior, and
persistent paths. Flip `schedule.enabled: true` when cloud credentials are
configured. The pipeline does NOT run continuously — it runs when triggered
by the scheduler or manually. A GitHub Actions workflow (`.github/workflows/`)
is provided for scheduled cloud execution.

## YouTube publishing

Publishing is implemented as an optional dry-run mode. Real upload requires:
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
  environment variables (or equivalent secret storage).
- Explicit confirmation before the first real upload.
- Official YouTube Data API v3 interfaces when credentials are configured.

No upload is claimed successful without confirmation from the service.

## What is NOT implemented / limitations

- eSpeak NG TTS is intelligible but not human-natural; voice limitations are
  documented rather than pretended.
- No Blender 3D animation; lightweight 2D Pillow animation is used for
  reliability.
- YouTube upload is dry-run only until credentials and explicit approval are
  provided.
- No local LLM on the phone; research uses online sources when networking is
  available, otherwise reports the failure and continues with supported
  material only.
- Maximum video duration enforced at 20 minutes (1200 seconds).
