# Synology Photo Tagger v0.4.22

A Python web app for browsing Synology Photos, generating photo descriptions and tags, and applying verified updates through the Synology Photos API.

## Current features

- Builds a resumable local metadata catalog through read-only Synology Photos API calls. Personal/shared spaces and NAS accounts are isolated. Metadata is stored in a separate SQLite file on the persistent Docker volume; original images are not downloaded or stored. Catalog synchronization currently includes photos, not videos.
- Uses offset pagination; if photos are added during a long synchronization, run another sync afterward. It retains catalog entries absent from NAS to avoid misclassifying pagination shifts as deletions.
- Searches the local catalog by date range, country, location, filename, description, camera, lens, exact tag, and exact Synology Photos person name. Query results show thumbnails proxied live from Synology Photos.
- Provides a read-only in-container Python query command: `docker exec -it SYNOLOGY-PHOTO-TAGGER python /app/scripts/query_photo_catalog.py --space personal --tag '產品'`. It prompts for the NAS account used to scope the local catalog and does not connect to NAS.

- Connects to Synology Photos through its API.
- Browses personal and shared spaces with paginated photo previews.
- Shows thumbnails through an authenticated proxy.
- Loads description, EXIF, resolution, GPS, location, and existing tags when a photo's metadata panel is opened.
- For a photo already tagged `產品`, looks up nearby OSM shops only when its metadata panel is opened; it shows Traditional Chinese display names with the map name beside them, distance, translated shop type, and OSM attribution. The GPS is sent to Photon; only public shop names and types are sent to the private MLX server for translation. Results are temporary candidates and are never written to Synology Photos.
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
- Supports daily AI tagging schedules that query photos taken today and yesterday through the Photos API date filter, then reuse the selected job settings.
- Can register a Synology trusted device for unattended schedule login. The NAS password and device ID are encrypted with a separate host-mounted key; TOTP is never stored. The trusted device can be revoked in DSM.
- Uses the UX-Deck Lucide squirrel mark as the browser favicon and app brand icon.

v0.4.8 narrows the default skip rule to photos with a recorded successful AI description or AI tag write. A successful tag rename alone does not exclude a photo; skipped photos are excluded before analysis, so the job will not request AI descriptions or additional tags for them. It retains v0.4.7's larger job metrics and removal of the misleading development label, along with v0.4.6's general photo descriptions and tags, automatic verified writes, and Dry run. Existing descriptions are preserved and not replaced; AI descriptions are added only when a photo has no description. Photos API writes may update original-file metadata. The application stores job records in SQLite on the persistent `tagger-data` volume, marks interrupted analysis as failed and interrupted writes as uncertain on restart, and never blindly retries an uncertain write. It does not store original photos or OCR text in job records. Browser login sessions can remain valid for up to 12 idle hours; the signing key persists on `tagger-data`, but NAS passwords and OTP codes are never stored. Restarting the container clears the in-memory NAS API session and may require a new login. The AI uses `證件` only for formal credentials meant to establish a holder’s identity; reports, forms, receipts, and test results are `文件` or a more specific content tag even when they contain a name or number. Batch tag replacement remains available in chunks of up to 25, with destination and source tag readback verification. Synology Photos API behavior can vary by DSM and Photos version.

## Quick start

Create a `.env` file with your NAS URL and local settings, and place the MLX and Tailscale keys in the host secret files referenced by `.env.example`. Then run:

```sh
docker compose up -d
```

For local development, open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos. Production deployment binds the web port to NAS loopback and requires HTTPS through a reverse proxy.

# Synology Photo Tagger v0.4.22

The provided Compose file uses the versioned `v0.4.22` image tag. It includes a metadata-only catalog that can be synchronized per Photos space, resumed after interruption, and searched locally. Search matching rules and direct Python query examples are documented in the repository README. Results are not a live NAS index until synchronization is complete; thumbnails are fetched through the authenticated Photos API on demand. AI writes verified through the Photos API also receive the `Photo Tagger AI v1` tag. The separate version-upgrade workflow can reanalyze photos found from Photo Tagger's successful-write history, an older version tag, or user-selected filters for photos without a version tag. Dry runs do not add the version tag; existing non-empty descriptions remain protected. The image also retains the `產品` nearby OpenStreetMap lookup, daily AI tagging with Synology trusted-device authentication, candidate caps up to 1,000, and automatic Photos API write/readback verification. Docker Hub retains only `vX.Y.Z` image tags. Keep MLX and Tailscale credentials in host secret files, not `.env`. Gunicorn runs as a non-root user, the Photos mount remains read-only, the host web binding defaults to loopback, and Compose applies memory, process, and capability limits. Tailscale state, AI job records, catalog metadata, and the session signing key persist in Docker volumes.

The connection warning is shown only when the browser reaches the app over remote HTTP. HTTPS and loopback access, including a localhost SSH tunnel, do not show it. Production also requires an HTTPS DSM address with certificate verification.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.4.22
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
