# Toutiao Video Extractor

A GitHub Actions based extractor for public Toutiao video links.

## What it does

Given a Toutiao short link such as `https://m.toutiao.com/is/...` or a direct `/video/{id}/` URL, the workflow:

1. Resolves the short link.
2. Reads Toutiao `RENDER_DATA`.
3. Decodes `playAuthTokenV2`.
4. Calls ByteDance VOD `GetPlayInfo` to obtain signed media URLs.
5. Downloads the real MP4.
6. Extracts a 16 kHz mono WAV.
7. Transcribes the real audio with faster-whisper.
8. Uploads all outputs as a GitHub Actions artifact.

## Run manually

Open `Actions -> Toutiao Video Extractor -> Run workflow`.

Paste the Toutiao URL into the `url` input and run it.

The completed workflow uploads an artifact named `toutiao-extract-<run_id>`.

Typical artifact files:

- `video.mp4`
- `audio.wav`
- `transcript.txt`
- `transcript.json`
- `result.json`
- fetched page / RENDER_DATA / VOD metadata for diagnostics

## Trigger from another workflow

```yaml
jobs:
  extract:
    uses: whichow/whichow.github.io/.github/workflows/toutiao-video-extract.yml@master
    with:
      url: "https://m.toutiao.com/is/..."
```

## Trigger through GitHub API

The workflow accepts a `repository_dispatch` event of type `extract_toutiao_video` with a JSON payload containing `url`.

```json
{
  "event_type": "extract_toutiao_video",
  "client_payload": {
    "url": "https://m.toutiao.com/is/..."
  }
}
```

Use a GitHub token with permission to dispatch repository events. Do not put a GitHub token into a public web page.

## Entry points

- Workflow: `.github/workflows/toutiao-video-extract.yml`
- Extractor: `tools/toutiao_video_extract.py`
