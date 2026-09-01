# MATEbot 0.4.0 - profile control + `/doctor` + thermal READY detection

This package is based on the existing MATEbot 0.4.0 profile-control + simple
`/doctor` overlay. `/doctor full` is intentionally not included.

Adds:

- `matebot.warmup.WarmupTracker`;
- HEATING / OVERSHOOT / SETTLING / READY classification;
- dynamic per-cycle peak temperature capture;
- overshoot-gated ready detection;
- 20-second target-band stabilization requirement;
- `/doctor` thermal state output;
- `/status` compact thermal state output;
- `/wake` ready notification only after the post-overshoot settling phase.

Recommended image tag:

```text
matebot-profile-control:0.4.0-doctor-ready1
```

Build:

```bash
docker build \\
  -f Dockerfile.profile-control \\
  -t matebot-profile-control:0.4.0-doctor-ready1 \\
  .
```

Portainer:

```yaml
image: matebot-profile-control:0.4.0-doctor-ready1
pull_policy: never
```
