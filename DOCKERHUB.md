# Synology Photo Tagger v0.4.10

A Python web app for browsing Synology Photos, generating photo descriptions and tags, and applying verified updates through the Synology Photos API.

## Current features

- Connects to Synology Photos through its API.
- Browses personal and shared spaces with paginated photo previews.
- Shows thumbnails through an authenticated proxy.
- Loads description, EXIF, resolution, GPS, location, and existing tags when a photo's metadata panel is opened.
- Uses person names already assigned in Synology Photos as context for AI descriptions.
- Filters photo candidates by existing tag, including photos without tags, and can combine tag and Japan location filters. Tag options are gathered with a read-only scan of the selected space and show scan progress.
- Supports Japan location filtering and optional OTP login.
- Analyzes a selected photo through a private MLX server, then automatically writes valid descriptions and tags and verifies them by reading the item back through Synology Photos API.
- Verifies tag-writing behavior for the specified JPG and HEIC items only after explicit confirmation: it adds a unique temporary tag, reads it back, removes it, and compares original-file SHA-256 values through the Photos API.
- Supplies the currently signed-in user's selected-space tag names to the AI as a vocabulary; if the Photos API cannot provide them, analysis continues without borrowing another user's tags.
- Keeps the NAS session on the server and serves the original photo folder as a read-only mount.
- Creates a fixed candidate snapshot from personal/shared space, Japan location, date range, and existing-tag filters (maximum 1,000 candidates and 40 source pages; selectable caps: 50, 100, 200, 300, 500, 800, 1,000).
- Analyzes candidates one by one for a concise visual description and relevant tags, using the selected Photos space's existing tag vocabulary where appropriate.
- Automatically writes valid results and verifies each description and tag through the Photos API; invalid or empty analysis results are skipped.
- Skips photos with a recorded successful Photo Tagger AI description or tag write by default, with an option to include them; reports the excluded count. Detection is scoped to the signed-in account and selected Photos space. A tag rename by itself does not count as AI processing.
- Offers a Dry run mode that analyzes the same candidates and reports intended changes without calling Photos API write operations.
- Preserves existing photo descriptions: AI descriptions are written only when the current description is empty; existing descriptions are left unchanged while tag updates can proceed.
- Shows per-photo progress, verified writes, skipped items, failures, and uncertain writes; failed analysis can be retried, while uncertain writes require checking Photos before retrying.
- Downloads per-job JSON reports and removes only tag IDs that the job itself added when undoing tag changes.
- Persists job records and reports in SQLite on the `tagger-data` Docker volume. Original photos and OCR text are not stored in the job database.
- Keeps browser login sessions for up to 12 idle hours. For unattended schedules only, an explicitly registered Synology trusted-device credential is encrypted using a separate key file mounted read-only from the Docker host; the TOTP code is never stored.
- Marks candidate photos with Photo Tagger-added tags that remain present, including individual writes and reviewed tagging jobs; undone tags are excluded.
- Distinguishes identity credentials (`證件`) from general documents (`文件`) in AI tag suggestions.
- Replaces one existing tag with another across all photos carrying the source tag; the affected count is shown before confirmation and writes are processed in chunks of up to 25 with readback verification.
- Supports daily AI tagging schedules that scan photos taken on the run date and reuse the selected job settings.
- Can register a Synology trusted device for unattended schedule login. The NAS password and device ID are encrypted with a separate host-mounted key; TOTP is never stored. The trusted device can be revoked in DSM.

v0.4.8 narrows the default skip rule to photos with a recorded successful AI description or AI tag write. A successful tag rename alone does not exclude a photo; skipped photos are excluded before analysis, so the job will not request AI descriptions or additional tags for them. It retains v0.4.7's larger job metrics and removal of the misleading development label, along with v0.4.6's general photo descriptions and tags, automatic verified writes, and Dry run. Existing descriptions are preserved and not replaced; AI descriptions are added only when a photo has no description. Photos API writes may update original-file metadata. The application stores job records in SQLite on the persistent `tagger-data` volume, marks interrupted analysis as failed and interrupted writes as uncertain on restart, and never blindly retries an uncertain write. It does not store original photos or OCR text in job records. Browser login sessions can remain valid for up to 12 idle hours; the signing key persists on `tagger-data`, but NAS passwords and OTP codes are never stored. Restarting the container clears the in-memory NAS API session and may require a new login. The AI uses `證件` only for formal credentials meant to establish a holder’s identity; reports, forms, receipts, and test results are `文件` or a more specific content tag even when they contain a name or number. Batch tag replacement remains available in chunks of up to 25, with destination and source tag readback verification. Synology Photos API behavior can vary by DSM and Photos version.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the versioned `v0.4.10` image tag. This release adds candidate caps up to 1,000 and recurring daily AI tagging with Synology trusted-device authentication. Photo library filters do not become AI job criteria. Docker Hub retains only tags in the `vX.Y.Z` format; the publishing workflow removes floating (`latest`), commit (`sha-*`), and non-three-part version tags. Set `MLX_SERVER_URL`, `MLX_SERVER_API_KEY`, and a dedicated Tailscale `TAILSCALE_AUTHKEY` in `.env` to enable analysis. `MLX_OCR_ENGINE` selects `baidu` (default) or `glm` for document OCR. Tailscale node state and AI job records plus the session signing key persist in Docker named volumes. For schedules, create the host Fernet key file described in README and set `NAS_DOCKER_ROOT` and `NAS_SCHEDULE_KEY_SOURCE` in `.env` before deployment.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.4.10
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
