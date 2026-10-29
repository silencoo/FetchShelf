# CloakBrowser Video Download Recovery

This document records the approach that restored stable TikTok video downloads
for the local `TikTok-Api` vendor copy when running through CloakBrowser.

## Problem summary

The original vendor implementation was no longer reliable for our environment:

- `video.info()` requested page HTML with Python `requests.get(...)`.
- share URL expansion used `requests.head(...)`.
- non-stream video download still depended on direct HTTP client downloads.
- browser pages could load successfully, but the extra non-browser requests often
  received WAF or invalid responses.

After detail parsing was moved onto the active CloakBrowser page, image posts
started working again, but video downloads still failed because media URLs were
being fetched through `httpx` or page `fetch(...)`, which were still blocked.

## What finally worked

The successful path is based on three layers:

1. Use the active CloakBrowser page to obtain detail data.
2. Prefer historically successful media URLs when choosing candidates.
3. If direct HTTP fetch fails, trigger a real browser media load and capture the
   network response body from Playwright/CloakBrowser events.

## Detail path changes

- `TikTokApi.api.video.Video.info()` no longer uses `requests.get(self.url, ...)`.
- It now navigates the active browser page and parses the returned HTML for:
  - `#SIGI_STATE`
  - `#__UNIVERSAL_DATA_FOR_REHYDRATION__`
- This keeps detail retrieval inside the CloakBrowser session instead of issuing
  a separate Python HTTP request.

## Media URL policy

The current policy is no-watermark only.

Allowed video candidates now come only from:

- `playAddr`
- `PlayAddrStruct.UrlList`
- `bitrateInfo[*].PlayAddr.UrlList`

The implementation explicitly does not use `downloadAddr` anymore.

This means:

- if a no-watermark candidate succeeds, the download succeeds
- if all no-watermark candidates fail, the download fails
- there is no fallback to a watermarked result

## Video download strategy

Current order in `TikTokApi.api.video.Video.bytes()`:

1. Attempt browser-context binary fetch with `page.evaluate(fetch(...))`
2. If that fails, fall back to real media-response capture

The first method still often throws `TypeError: Failed to fetch` because TikTok
wraps page `fetch` with additional privacy/security layers. That error is now
treated as a request failure, not a session-death signal.

## Real media response capture

The key recovery was adding a browser-native fallback in
`TikTokApi.tiktok.TikTokApi.capture_media_response()`.

Implementation outline:

- attach a temporary `page.on("response")` listener
- inject a hidden `<video>` element into the page
- assign the candidate media URL as `video.src`
- call `video.load()` and try `video.play()`
- let the browser request the media naturally
- capture matching media responses from Playwright/CloakBrowser
- read the response body with `response.body()`
- return the best captured payload to `Video.bytes()`

This works because the browser performs a normal media request path instead of a
scripted `fetch(...)` path, which bypasses the failure mode we were seeing.

## Session handling changes

- failed media fetches no longer invalidate otherwise healthy sessions
- this allows multiple downloads to proceed in the same run even when some
  candidate URLs fail

## Demo behavior after patch

The demo downloader now supports:

- detail debugging with screenshots and HTML capture
- image-post downloads
- video downloads through CloakBrowser media response capture
- candidate reordering so preferred video samples are tested first

## Verified result

The current no-watermark-only path was verified with these runs:

- targeted no-watermark capture:
  - output directory: `demo/output_tiktok_nowm_only_test`
  - examples saved from `playAddr` / `PlayAddrStruct`
- demo no-watermark-only download:
  - output directory: `demo/output_tiktok_api_nowm_only_verify`
  - summary file: `demo/output_tiktok_api_nowm_only_verify/download_summary.json`

Observed successful examples included:

- `7593306286805093648` captured from no-watermark candidates only
- `7619259333494279442` downloaded via `bitrateInfo:normal_540_0`

## Why this solution is preferred for now

- It stays inside the CloakBrowser session for the sensitive parts.
- It avoids depending on Python `requests` for detail retrieval.
- It avoids relying solely on page `fetch(...)` for video media.
- It reuses real browser network behavior, which is currently the most reliable
  way we found to reach TikTok media responses.
- It enforces the product requirement that only no-watermark video is acceptable.

## Remaining notes

- `page.evaluate(fetch(...))` still fails often and is retained only as an
  earlier attempt/fallback layer.
- If TikTok changes media-loading behavior again, the first place to inspect is
  the response-capture fallback in `capture_media_response()`.
- If needed later, this approach can be extended with more explicit filtering of
  media responses or response artifact persistence for debugging.
