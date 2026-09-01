# `/doctor` diagnostics

The custom MATEbot image adds a read-only `/doctor` command.

It checks:

- MATEbot package version and runtime;
- state persistence / writability;
- messenger/config baseline;
- GaggiMate status freshness, mode, temperatures, water and status profile;
- thermal warm-up phase, dynamic peak temperature, post-overshoot READY state
  and peak-to-ready settle duration;
- GaggiMate profile API, profile counts and selected-profile consistency;
- GaggiMate history index;
- latest active shot vs MATEbot `last_shot_id`;
- latest Shot Notes availability.

It deliberately does **not**:

- select or edit profiles;
- save Shot Notes;
- change machine mode;
- start a brew;
- run OTA operations.

Telegram:

```text
/doctor
```

Typical result:

```text
🩺 MATEbot Doctor

MATEbot
✅ Version 0.4.0
✅ Runtime 2h 14m
✅ State writable · /data/state
✅ Messenger telegram · command channel active
✅ Archive/journal sync disabled (simple mode)

GaggiMate
Host 192.168.1.100
✅ Live status fresh · 180 ms
✅ Mode brew
Temperature 94.2 °C → 94.0 °C
Water 80%
Status profile Burundi Mubuga
✅ Thermal state READY · stable 24 s
Warm-up peak 99.7 °C · overshoot +5.7 °C · settled in 46s

Profiles
✅ Profile API · 17 profiles
Normal 14 · Favorites 6 · Utility 3
✅ Selected · Burundi Mubuga

History
✅ History index · 151 active shots
next_id 152
Latest GaggiMate shot #151
Last MATEbot shot #151
✅ Shot IDs synchronized
✅ Latest Shot Notes present · rating 5/5

Result
🟢 HEALTHY
9 passed · 0 warnings · 0 errors
```
