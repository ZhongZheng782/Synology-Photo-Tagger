# Synology Photo Tagger v0.3.19

A lightweight Python web app for browsing a Synology Photos library and inspecting photo metadata before building an AI tagging workflow.

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

This v0.3.19 release lets a signed-in user review and edit an AI description and suggested tags, then explicitly confirm writing them to the selected Synology Photos item. The app uses the Photos API, creates or resolves tag IDs, writes the description and tags, then reads the item back to verify them. A description replaces the current description; selected tags are added without removing existing tags. Synology Photos may rewrite original-file metadata, content, size, or modification time. The write form explains the effects next to the submit button; clicking it starts the write without a second confirmation dialog. The prior JPG/HEIC API write check verified Photos can read/write tags on IDs 82153 and 82155; the JPG test changed file bytes, while the HEIC test did not. It includes an inventory of existing Synology Photos tags and their item counts. During photo analysis, the app reads tag names from the currently signed-in user's selected Photos space and asks the model to reuse exact existing names when relevant, proposing new terms only when the current vocabulary has no good fit. If the tag API is unavailable, analysis proceeds without a vocabulary; another user's tags are never used. Usage counts do not affect relevance, and person tags can only use names confirmed in the selected photo metadata. For an explicitly selected photo, the app retrieves the original and person/location metadata through the Synology Photos API. Analysis requests fetch the same metadata as the photo details panel. Confirmed Synology Photos names and GPS-derived place names are supplied as context for the AI description; Photo Tagger does not infer which face corresponds to each name or identify a landmark from coordinates alone. The app holds the original in memory and uploads it once to the private MLX server for visual suggestions; if those identify a scanned document, the server runs OCR asynchronously using the same request-scoped image file. Original retrieval and analysis run in a background job, while the browser polls short status requests to avoid gateway timeouts. The UI distinguishes queued OCR (waiting) from active OCR (processing) and shows elapsed time. Neither the original nor OCR output is saved by Photo Tagger. Tailscale userspace networking provides an HTTP proxy for MLX requests without granting the container network administration capabilities. The web server uses threads so long analysis requests do not block other UI requests. Synology Photos API behavior can vary by DSM and Photos version.

## Quick start

Create a `.env` file with your NAS URL and local settings, then run:

```sh
docker compose up -d
```

Open `http://localhost:5056/`. Set `SYNOLOGY_URL` to the DSM address reachable from the container. Sign in through the web UI with a Synology account that can access Photos.

The provided Compose file uses the `v0.3.19` image tag. Set `MLX_SERVER_URL`, `MLX_SERVER_API_KEY`, and a dedicated Tailscale `TAILSCALE_AUTHKEY` in `.env` to enable analysis. `MLX_OCR_ENGINE` selects `baidu` (default) or `glm` for document OCR. Tailscale node state persists in a Docker named volume. To run the latest published build instead, change the image tag to `latest`.

## Image

```sh
docker pull wenchiehlee1020/synology-photo-tagger:v0.3.19
```

Source: [GitHub](https://github.com/ZhongZheng782/Synology-Photo-Tagger)
