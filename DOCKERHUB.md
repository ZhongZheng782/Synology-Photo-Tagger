# Synology Photo Tagger v0.3.7

A lightweight Python web app for browsing a Synology Photos library and inspecting photo metadata before building an AI tagging workflow.

## Current features

- Connects to Synology Photos through its API.
- Browses personal and shared spaces with paginated photo previews.
- Shows thumbnails through an authenticated proxy.
- Loads description, EXIF, resolution, GPS, location, and existing tags when a photo's metadata panel is opened.
- Filters photo candidates by existing tag, including photos without tags, and can combine tag and Japan location filters. Tag options are gathered with a read-only scan of the selected space and show scan progress.
- Supports Japan location filtering and optional OTP login.
- Analyzes one selected photo through a private MLX server and displays Traditional Chinese description and tag suggestions. Analysis is opt-in per photo and does not write to Synology Photos.
- Keeps the NAS session on the server and serves the original photo folder as a read-only mount.

This v0.3.7 release remains read-only: it does not write tags or descriptions. For an explicitly selected photo, the app retrieves the original through the Synology Photos API and holds it in memory. It uploads the image once to the private MLX server for visual suggestions; if those identify a scanned document, the server runs OCR asynchronously using the same request-scoped image file. Original retrieval and analysis run in a background job, while the browser polls short status requests to avoid gateway timeouts. The UI distinguishes queued OCR (waiting) from active OCR (processing) and shows elapsed time. Neither the original nor OCR output is saved by Photo Tagger. Tailscale userspace networking provides an HTTP proxy for MLX requests without granting the container network administration capabilities. The web server uses threads so long analysis requests do not block other UI requests. Synology Photos API behavior can vary by DSM and Photos version; metadata fields should be checked against the target NAS.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the `v0.3.7` image tag. Set `MLX_SERVER_URL`, `MLX_SERVER_API_KEY`, and a dedicated Tailscale `TAILSCALE_AUTHKEY` in `.env` to enable analysis. `MLX_OCR_ENGINE` selects `baidu` (default) or `glm` for document OCR. Tailscale node state persists in a Docker named volume. To run the latest published build instead, change the image tag to `latest`.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.3.7
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
