# MATEbot `/doctor` patch summary

Target base: MATEbot 0.4.0 + the previously applied Telegram profile-control overlay.

Adds:

- `/doctor` to the common command router and `/help`;
- `matebot.diagnostics` read-only diagnostics module;
- state writability check;
- live GaggiMate status freshness check;
- machine mode / temperature / water / profile summary;
- profile API health and selected-profile consistency check;
- GaggiMate history index check;
- GaggiMate latest-shot vs MATEbot `last_shot_id` reconciliation;
- latest Shot Notes presence check;
- summary severity: HEALTHY / HEALTHY WITH WARNINGS / PROBLEMS FOUND.

The command performs no machine-changing action.

## Recommended image tag

```text
matebot-profile-control:0.4.0-doctor1
```

## Build

```bash
docker build \
  -f Dockerfile.profile-control \
  -t matebot-profile-control:0.4.0-doctor1 \
  .
```

## Portainer

```yaml
image: matebot-profile-control:0.4.0-doctor1
pull_policy: never
```

## Test

```text
/doctor
```

Validation performed on the supplied MATEbot source overlay:

```text
11 passed
```
