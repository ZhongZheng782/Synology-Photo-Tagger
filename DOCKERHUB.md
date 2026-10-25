# Synology Photo Tagger v0.2

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

This v0.2 release remains read-only: it does not write tags or descriptions. For an explicitly selected photo, the app retrieves the original through the Synology Photos API, temporarily holds it in memory, and sends it to the configured private MLX server. It does not save the original to the app container or return it to the browser. Synology Photos API behavior can vary by DSM and Photos version; metadata fields should be checked against the target NAS.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the `v0.2` image tag. Set `MLX_SERVER_URL` and `MLX_SERVER_API_KEY` in `.env` to enable analysis. To run the latest published build instead, change the image tag to `latest`.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.2
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
