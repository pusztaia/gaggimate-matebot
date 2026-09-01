# `/doctor` thermal-ready diagnostics

This package extends the **simple `/doctor`** build.  It does not include
`/doctor full`.

It adds a thermal warm-up state machine driven only by documented GaggiMate
`evt:status` values:

```text
ct = current temperature
tt = target temperature
m  = machine mode
```

Warm-up states:

```text
IDLE -> HEATING -> OVERSHOOT -> SETTLING -> READY
                   ^               |
                   |               v
                target+3C     target ±0.7C for 20 s
```

The exact peak is measured dynamically.  `99.7 C` is **not** hard-coded.

Once READY, `/doctor` and the `/wake` ready notification also report how long
it took to come back down from that peak into the stable ready band (the
"settled in" duration below) — a single measurement taken once per warm-up
cycle, preserved even if the target temperature changes and forces a
re-settle.

## MATEbot operational thresholds

```text
overshoot detected: peak >= target + 3.0 C
settling detected:  temperature falls at least 0.3 C from peak
ready band:         target ±0.7 C
ready stability:    20 continuous seconds inside ready band
```

These are MATEbot heuristics, not GaggiMate firmware constants.

## Important behavior change

The previous wake notification fired as soon as:

```text
current >= target - 1 C
```

That could happen while the boiler was still heating toward its startup
overshoot.

The new notification fires only after:

1. brew mode is active;
2. a thermal overshoot has been observed;
3. temperature has returned to the target band;
4. temperature has remained in that band for 20 continuous seconds.

Example:

```text
94.0 target
  -> 94.0   target crossed, NOT READY
  -> 97.0   heating
  -> 99.7   OVERSHOOT
  -> 97.4   SETTLING
  -> 94.5   SETTLING, stability timer starts
  -> 94.2   after 20 s -> READY
```

Telegram `/doctor` example during settling:

```text
GaggiMate
Host 192.168.50.68
✅ Live status fresh · 220 ms
✅ Mode brew
Temperature 97.2 °C -> 94.0 °C
Status profile Burundi Mubuga
🟠 Thermal state SETTLING · not ready yet
Warm-up peak 99.7 °C · overshoot +5.7 °C
```

After stabilization:

```text
✅ Thermal state READY · stable 24 s
Warm-up peak 99.7 °C · overshoot +5.7 °C · settled in 46s
```

`/status` also includes a compact warm-up state.

## Safety

The thermal tracker is read-only. It does not change PID values, profile
temperature, machine mode, or brew parameters.
