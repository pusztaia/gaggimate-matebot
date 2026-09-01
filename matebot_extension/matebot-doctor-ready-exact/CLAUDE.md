# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This is **not** a standalone application — it's an *overlay patch* for a third-party Docker image, [`ghcr.io/alexnly/matebot`](https://github.com/alexnly/matebot) (a Telegram/Discord bot for GaggiMate espresso machines). The base image ships a full `matebot` Python package; this repo replaces a handful of files inside that installed package via a Docker build step, layering in three features not present upstream: Telegram profile control, a read-only `/doctor` diagnostics command, and overshoot-aware thermal "ready" detection.

Everything lives under `package/`:

- `package/src/matebot/` — full replacement copies of the affected files from `matebot` 0.4.0 (`cli.py`, `commands.py`, `machine.py`, `profiles.py`, `diagnostics.py`, `warmup.py`, `messengers/telegram.py`). Only `diagnostics.py`, `warmup.py`, and `tests/test_warmup.py` are new; the rest are the upstream files with changes applied, kept whole (not diffs) so the Dockerfile can just `shutil.copy2` them over the base image's installed package.
- `package/Dockerfile.profile-control` — builds `FROM ghcr.io/alexnly/matebot:latest`, verifies the installed version is exactly `0.4.0` (fails the build otherwise — this repo has no baseline other than that exact version), then overwrites the listed files inside the installed package and drops back to `USER 1000:1000`.
- `package/12-matebot-doctor-ready.yaml` — the Portainer/Compose stack for deploying the built local image (numbering `12-` implies it slots into a broader home-server stack collection, deployed after other infra like the reverse proxy).
- `package/*.patch` — reference-only unified diffs (`matebot-profile-control.patch`, `matebot-doctor-ready.patch`) showing what changed relative to the upstream baseline / the previous overlay layer. These are historical records, not something to `git apply` in normal workflows — the `src/matebot/*.py` files are already the patched result.
- `package/tests/` — unit tests for the one fully self-contained module, `warmup.py`.
- `package/README.md`, `DOCTOR.md`, `DOCTOR_READY.md`, `PATCH_SUMMARY*.md` — user-facing docs for each layered feature; read these before changing behavior they describe, since they encode the exact Telegram output format users see.

## Key constraint: files are incomplete outside the base image

`package/src/matebot/` only contains the files this overlay touches. Modules they import from (`config`, `conversation`, `state`, `watcher`, `messengers.base`, `slog`, `sync`, `bags`, `hints`, `video`, `calibrate`, `render`, `digest`, `camera`, `plot`, `sitegen`, etc.) are **not in this repo** — they come from the upstream `matebot` 0.4.0 package inside the base image. You cannot `pip install -e` or run this package standalone; static analysis/imports of the overlay files outside the built container will fail on those missing modules. Only `warmup.py` (and by extension `test_warmup.py`) has no such dependency and can be exercised in isolation.

## Commands

Run the one self-contained test suite (only covers `warmup.py`):

```bash
cd package
python3 -m pytest tests/
```

There is no lint/format tooling and no project manifest (no `pyproject.toml`/`requirements.txt`) — dependencies are whatever the upstream `matebot:latest` base image already has installed.

Build the overlay image (requires Docker; must be run on the same host that will deploy it, since the Compose stack uses `pull_policy: never`):

```bash
cd package
docker build -f Dockerfile.profile-control -t matebot-profile-control:0.4.0-doctor-ready1 .
```

Smoke-test the built image without starting the bot:

```bash
docker run --rm --entrypoint python matebot-profile-control:0.4.0-doctor-ready1 \
  -c 'import matebot.profiles, matebot.diagnostics, matebot.warmup; print("profile + doctor + warmup OK")'
```

Deploy via Portainer using `package/12-matebot-doctor-ready.yaml` (or update the `image:` tag in an existing stack). It expects the built image to already exist locally on the Docker host — Diun is disabled (`diun.enable: "false"`) for this custom image since it can't check a registry for updates.

## Architecture of the layered features

### Thermal warm-up tracking (`warmup.py`, wired into `commands.py`)

`WarmupTracker.observe(frame, now)` is a pure state machine driven only by GaggiMate `evt:status` fields (`ct` current temp, `tt` target temp, `m` mode). It exists because the naive "ready when current ≈ target" check fired too early: this machine's startup warm-up overshoots the target before settling back down.

States: `IDLE -> HEATING -> OVERSHOOT -> SETTLING -> READY` (see `DOCTOR.md` for the full diagram). Thresholds (not GaggiMate firmware constants — MATEbot-side heuristics):
- overshoot: peak reaches `target + 3.0°C`
- settling: temperature has fallen ≥0.3°C from the observed peak
- ready: current temp within `target ± 0.7°C` for 20 continuous **seconds**
- leaving brew mode (`m != 1`) resets the cycle to `IDLE`
- changing the target while `READY` requires re-settling into the new band, but does *not* require a fresh overshoot

`CommandRouter` in `commands.py` holds one `WarmupTracker` instance per session and surfaces its snapshot in both `/status` (compact) and `/doctor` (verbose, with peak/overshoot numbers) output. The `/wake` ready notification is gated on `WarmupSnapshot.ready`, not on raw temperature comparison. This tracker is read-only — it never writes PID values, profile temperature, mode, or brew parameters (see `DOCTOR.md` "Safety").

### Profile control (`profiles.py`, wired into `commands.py`)

`ProfileService` wraps the GaggiMate WebSocket profile RPCs (`req:profiles:list`, `req:profiles:load`, `req:profiles:select` — added to `GaggiMateClient` in `machine.py`) and adds messenger-agnostic pagination/formatting (`paginate_profiles`, `format_current`, `format_detail`) plus opaque callback-id encode/decode (`encode_callback`/`decode_callback`, kept under the 64-byte Telegram callback-data limit). It reuses the base `Option`/`OptionSelected` messenger abstraction (see `cli.py`'s dispatch of `OptionSelected` events to `router.handle_option`) so Telegram's inline buttons and Discord's button view share one code path — no messenger-specific branching for profile selection.

Safety invariants enforced in `ProfileService`, not the UI layer: utility/maintenance profiles are hidden from normal browsing and rejected if selected directly; profile changes are blocked while a brew is active (`ProfileSelectionBlocked`); selection state is re-read from GaggiMate after every change rather than assumed.

### Diagnostics (`diagnostics.py`)

`run_doctor(...)` is a single async function that performs a fixed, ordered sequence of read-only checks against MATEbot state and the live GaggiMate client (state writability, live status freshness, mode/temp/water/profile summary, warmup phase, profile API health, history index, shot-id reconciliation, Shot Notes presence) and returns a `DoctorReport` whose rendering determines the HEALTHY / HEALTHY WITH WARNINGS / PROBLEMS FOUND verdict shown in Telegram. It deliberately performs no mutating action (see `DOCTOR.md` "It deliberately does not..."). When adding a new check, follow the existing pattern: one check = one line in the report, contributing to pass/warn/error counts, never throwing on a machine-side failure (report it as a warning/error instead).

### `GaggiMateClient` (`machine.py`)

Async WebSocket + HTTP client for the ESP32-based GaggiMate controller. The module docstring documents several non-obvious firmware behaviors that must not be "fixed" away: the ESP32 drops WS clients whenever its send queue fills (treat 15s silence as dead, reconnect with capped exponential backoff via `status_stream()`); missing `/api/history/*` files 200 with the SPA's `index.html` (always content-validate downloads, e.g. `fetch_slog`'s `is_slog` check, never trust the HTTP status alone); `notes_save` writes under both zero-padded and unpadded shot-id filenames because firmware builds disagree on which one the UI reads back.

## Working conventions in this repo

- When editing any file under `package/src/matebot/`, keep in mind it's a **complete replacement file**, not a diff — the Dockerfile copies it wholesale over the base image's version. Preserve everything from the upstream 0.4.0 baseline that this overlay doesn't intend to change (check the `.patch` files if unsure what's original vs. added).
- Match the version pin: the Dockerfile hard-fails if the base image's installed `matebot` isn't exactly `0.4.0`. If bumping to a newer upstream base, re-diff against the new baseline (don't assume the overlay files still apply cleanly) and update the version check.
- Update the corresponding `PATCH_SUMMARY*.md` / `DOCTOR*.md` / `README.md` when changing user-visible behavior (command output formats, thresholds, new commands) — these files are the canonical description of exact Telegram wording users should expect, and `DOCTOR.md`/`DOCTOR_READY.md` show literal example output blocks that should stay accurate.
- Never inline secrets (Telegram bot token/chat id) — the stack YAML already reads them from mounted files under `/run/secrets/`, matching the pattern used elsewhere in the broader home-server stack collection this Portainer file belongs to.
- Recommended image tags increment per feature layer (`...-1`, `...-doctor1`, `...-doctor-ready1`); follow that convention rather than reusing a tag when behavior changes, since `pull_policy: never` means Portainer won't otherwise notice a rebuilt image under the same tag.
