# MATEbot 0.4.0 - Profile Control + /doctor + Thermal READY

This is the **simple `/doctor`** branch with Telegram profile control and
thermal readiness detection. It intentionally does **not** include `/doctor full`.

## What changed

The original MATEbot ready notification considered the machine ready as soon as
current temperature reached roughly the profile target. On this machine the
startup warm-up continues beyond the target, reaches an overshoot (for example
99.7 C), then cools back to the selected profile temperature.

This build tracks that cycle:

```text
HEATING -> OVERSHOOT -> SETTLING -> READY
```

READY requires:

```text
observed peak >= target + 3.0 C
then current temperature inside target +/- 0.7 C
for 20 continuous seconds
```

The peak is measured dynamically; 99.7 C is not hard-coded.

## Build

```bash
cd matebot-doctor-ready-exact/package

docker build \
  -f Dockerfile.profile-control \
  -t matebot-profile-control:0.4.0-doctor-ready1 \
  .
```

Verify:

```bash
docker run --rm \
  --entrypoint python \
  matebot-profile-control:0.4.0-doctor-ready1 \
  -c 'import matebot.profiles, matebot.diagnostics, matebot.warmup; print("profile + doctor + warmup OK")'
```

## Portainer

Use `12-matebot-doctor-ready.yaml`, or change the image in the existing stack:

```yaml
image: matebot-profile-control:0.4.0-doctor-ready1
pull_policy: never
```

Keep Diun disabled for the local custom image.

## Telegram checks

```text
/status
/doctor
/profile
/profiles
/profiles all
```

During warm-up `/doctor` may show:

```text
🟠 Thermal state HEATING · not ready yet
```

then:

```text
🟠 Thermal state OVERSHOOT · not ready yet
Warm-up peak 99.7 °C · overshoot +5.7 °C
```

then:

```text
🟠 Thermal state SETTLING · not ready yet
Stable 12/20 s inside ±0.7 °C band
```

and finally:

```text
✅ Thermal state READY · stable 20 s
```

The `/wake` ready notification now waits for this final state.
