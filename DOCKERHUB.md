# Synology Photo Tagger v0.4.1

A Python web app for browsing Synology Photos, analyzing candidate photos, and managing reviewed AI tagging jobs.

## Current features

- Connects to Synology Photos through its API.
- Browses personal and shared spaces with paginated photo previews.
- Shows thumbnails through an authenticated proxy.
- Loads description, EXIF, resolution, GPS, location, and existing tags when a photo's metadata panel is opened.
- Uses person names already assigned in Synology Photos as context for AI descriptions.
- Filters photo candidates by existing tag, including photos without tags, and can combine tag and Japan location filters. Tag options are gathered with a read-only scan of the selected space and show scan progress.
- Supports Japan location filtering and optional OTP login.
- Analyzes one selected photo through a private MLX server and displays Traditional Chinese description and tag suggestions. Analysis is opt-in per photo and does not write to Synology Photos.
- Verifies tag-writing behavior for the specified JPG and HEIC items only after explicit confirmation: it adds a unique temporary tag, reads it back, removes it, and compares original-file SHA-256 values through the Photos API.
- Supplies the currently signed-in user's selected-space tag names to the AI as a vocabulary; if the Photos API cannot provide them, analysis continues without borrowing another user's tags.
- Keeps the NAS session on the server and serves the original photo folder as a read-only mount.
- Creates a fixed candidate snapshot from selected personal/shared space, Japan location, and existing-tag filters (maximum 300 candidates and 40 source pages).
- Analyzes candidates one by one for a shopping task and shows thumbnail, evidence, confidence, and description for human review.
- Lets the signed-in user accept, reject, or choose an existing tag from their selected Photos space; “購物” can be created when accepted.
- Writes only accepted items after the user presses the job write button, then reads back and verifies each result through the Photos API.
- Downloads a per-job JSON report, safely retries failed analysis, and removes only tag IDs that the job itself added.
- Persists job records and reports in SQLite on the `tagger-data` Docker volume. Original photos and OCR text are not stored in the job database.
- Keeps browser login sessions for up to 12 idle hours without saving the NAS password or OTP; a signing key is generated once and kept on the same persistent volume.

This release includes the v0.4.0 persistent, per-job AI tagging workflow. Jobs snapshot filtered candidates, analyze the shopping task, and present each photo for human review. Users can accept, reject, or choose an existing tag in their selected Photos space; accepting “購物” may create that tag if needed. Nothing is written until the user clicks “寫入已接受項目”. Each accepted photo is updated and read back through the Photos API. Job reports record outcomes; undo removes only tag IDs added by that job. Candidate snapshots are limited to 300 items and 40 source pages and disclose when the scan is incomplete. SQLite stores candidate display fields, analysis summaries, review decisions, and write/undo outcomes in the persistent `tagger-data` named volume. It does not store original photos or OCR output. Existing individual-photo analysis and confirmed description/tag editing remain available. Browser login sessions now remain valid for up to 12 idle hours; the signing key persists on `tagger-data`, but NAS passwords and OTP codes are never stored. Restarting the container clears the in-memory NAS API session and may require a new login. Synology Photos API behavior can vary by DSM and Photos version.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the versioned `v0.4.1` image tag. Docker Hub retains only tags in the `vX.Y.Z` format; the publishing workflow removes floating (`latest`), commit (`sha-*`), and non-three-part version tags. Set `MLX_SERVER_URL`, `MLX_SERVER_API_KEY`, and a dedicated Tailscale `TAILSCALE_AUTHKEY` in `.env` to enable analysis. `MLX_OCR_ENGINE` selects `baidu` (default) or `glm` for document OCR. Tailscale node state and AI job records plus the session signing key persist in Docker named volumes.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.4.1
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
