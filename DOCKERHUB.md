# Synology Photo Tagger v0.1

A lightweight Python web app for browsing a Synology Photos library and inspecting photo metadata before building an AI tagging workflow.

## Current features

- Connects to Synology Photos through its API.
- Browses personal and shared spaces with paginated photo previews.
- Shows thumbnails through an authenticated proxy.
- Loads description, EXIF, resolution, GPS, location, and existing tags when a photo's metadata panel is opened.
- Filters photo candidates by existing tag, including photos without tags, and can combine tag and Japan location filters. Tag options are gathered with a read-only scan of the selected space and show scan progress.
- Supports Japan location filtering and optional OTP login.
- Keeps the NAS session on the server and serves the original photo folder as a read-only mount.

This v0.1 release is read-only. It does not write tags or descriptions, download original photos, or run AI analysis. Synology Photos API behavior can vary by DSM and Photos version; metadata fields should be checked against the target NAS.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the `v0.1` image tag. To run the latest published build instead, change the image tag to `latest`.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.1
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
