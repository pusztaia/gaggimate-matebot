"""Read-only operational diagnostics for MATEbot + GaggiMate."""

from __future__ import annotations

import asyncio
import importlib.metadata
import time
from dataclasses import dataclass, field
from typing import Any

from .profiles import ProfileSummary
from .warmup import READY_BAND_C, READY_STABLE_S, WarmupPhase, WarmupSnapshot


MODE_NAMES = {0: "standby", 1: "brew", 2: "steam", 3: "water", 4: "grind"}


@dataclass(slots=True)
class DoctorReport:
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    passed: int = 0
    warnings: int = 0
    errors: int = 0

    def section(self, title: str, *lines: str) -> None:
        self.sections.append((title, list(lines)))

    def ok(self, text: str) -> str:
        self.passed += 1
        return f"✅ {text}"

    def warn(self, text: str) -> str:
        self.warnings += 1
        return f"🟠 {text}"

    def error(self, text: str) -> str:
        self.errors += 1
        return f"🔴 {text}"

    @property
    def status(self) -> str:
        if self.errors:
            return "🔴 PROBLEMS FOUND"
        if self.warnings:
            return "🟠 HEALTHY WITH WARNINGS"
        return "🟢 HEALTHY"

    def render(self) -> str:
        out = ["🩺 MATEbot Doctor", ""]
        for title, lines in self.sections:
            out.append(title)
            out.extend(lines)
            out.append("")
        out.extend(
            [
                "Result",
                self.status,
                f"{self.passed} passed · {self.warnings} warnings · {self.errors} errors",
            ]
        )
        return "\n".join(out)


def _fmt_age(age: float) -> str:
    if age < 1:
        return f"{age * 1000:.0f} ms"
    if age < 60:
        return f"{age:.1f} s"
    return f"{age / 60:.1f} min"


def _fmt_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _latest_history_entry(index: Any) -> Any | None:
    entries = [
        entry
        for entry in getattr(index, "entries", [])
        if getattr(entry, "completed", False) and not getattr(entry, "deleted", False)
    ]
    return max(entries, key=lambda entry: entry.id, default=None)


async def run_doctor(
    client: Any,
    state: Any,
    config: Any,
    latest_frame: Any,
    *,
    started_at: float,
    warmup: WarmupSnapshot | None = None,
) -> DoctorReport:
    """Run read-only diagnostics and return a compact report.

    No profile selection, Shot Notes save, mode change, or other machine mutation
    is performed here.
    """

    report = DoctorReport()

    # -------------------------------------------------------------- MATEbot
    try:
        version = importlib.metadata.version("matebot")
        version_line = report.ok(f"Version {version}")
    except Exception as exc:  # noqa: BLE001
        version_line = report.warn(f"Version unavailable ({type(exc).__name__})")

    try:
        persistent = bool(state.persistent)
    except Exception as exc:  # noqa: BLE001
        persistent = False
        state_line = report.error(f"State persistence check failed ({exc})")
    else:
        state_line = (
            report.ok(f"State writable · {config.state_dir}")
            if persistent
            else report.error(f"State is memory-only · {config.state_dir}")
        )

    archive_line = (
        report.warn(f"Archive/journal enabled · {config.data_repo}")
        if getattr(config, "data_repo", "")
        else report.ok("Archive/journal sync disabled (simple mode)")
    )

    report.section(
        "MATEbot",
        version_line,
        report.ok(f"Runtime {_fmt_uptime(time.monotonic() - started_at)}"),
        state_line,
        report.ok(f"Messenger {getattr(config, 'messenger', '?')} · command channel active"),
        archive_line,
    )

    # -------------------------------------------------------------- live WS
    frame, age = latest_frame()
    machine_online = frame is not None and age < 20
    machine_lines: list[str] = [f"Host {getattr(config, 'machine_host', '?')}"]

    if not machine_online:
        if frame is None:
            machine_lines.append(report.error("No GaggiMate status frame received"))
        else:
            machine_lines.append(report.error(f"Status stream stale · last frame {_fmt_age(age)} ago"))
        machine_lines.append(report.warn("Profile/history diagnostics may be incomplete while offline"))
    else:
        mode = MODE_NAMES.get(frame.get("m"), str(frame.get("m", "?")))
        machine_lines.append(report.ok(f"Live status fresh · {_fmt_age(age)}"))
        machine_lines.append(report.ok(f"Mode {mode}"))
        ct = frame.get("ct")
        tt = frame.get("tt")
        if isinstance(ct, (int, float)):
            temp = f"Temperature {ct:.1f} °C"
            if isinstance(tt, (int, float)) and tt:
                temp += f" → {tt:.1f} °C"
            machine_lines.append(temp)
        if frame.get("wl") is not None:
            machine_lines.append(f"Water {frame['wl']}%")
        if frame.get("p"):
            machine_lines.append(f"Status profile {frame['p']}")

        if warmup is not None and frame.get("m") == 1:
            if warmup.ready:
                machine_lines.append(
                    report.ok(
                        f"Thermal state READY · stable {warmup.stable_for_s:.0f} s"
                    )
                )
            elif warmup.phase in {
                WarmupPhase.HEATING,
                WarmupPhase.OVERSHOOT,
                WarmupPhase.SETTLING,
                WarmupPhase.OBSERVING,
            }:
                machine_lines.append(
                    report.warn(f"Thermal state {warmup.phase.value} · not ready yet")
                )

            if warmup.peak_c is not None and warmup.target_c is not None:
                over = warmup.peak_c - warmup.target_c
                peak_line = f"Warm-up peak {warmup.peak_c:.1f} °C · overshoot {over:+.1f} °C"
                if warmup.settle_duration_s is not None:
                    peak_line += f" · settled in {warmup.settle_duration_s:.0f}s"
                machine_lines.append(peak_line)
            if warmup.phase == WarmupPhase.SETTLING and warmup.in_ready_band:
                machine_lines.append(
                    f"Stable {warmup.stable_for_s:.0f}/{READY_STABLE_S:.0f} s "
                    f"inside ±{READY_BAND_C:.1f} °C band"
                )

    report.section("GaggiMate", *machine_lines)

    # -------------------------------------------------------------- profiles
    profile_lines: list[str] = []
    profiles: list[ProfileSummary] = []
    try:
        raw_profiles = await asyncio.wait_for(client.profiles_list(), timeout=8.0)
        profiles = [ProfileSummary.from_payload(p) for p in raw_profiles]
    except Exception as exc:  # noqa: BLE001
        profile_lines.append(report.error(f"Profile API failed · {type(exc).__name__}: {exc}"))
    else:
        selected = [p for p in profiles if p.selected]
        favorites = sum(p.favorite for p in profiles)
        utilities = sum(p.utility for p in profiles)
        normal = len(profiles) - utilities
        profile_lines.append(report.ok(f"Profile API · {len(profiles)} profiles"))
        profile_lines.append(f"Normal {normal} · Favorites {favorites} · Utility {utilities}")
        if len(selected) == 1:
            profile_lines.append(report.ok(f"Selected · {selected[0].label}"))
            if machine_online and frame.get("p") and frame.get("p") != selected[0].label:
                profile_lines.append(
                    report.warn(
                        f"Status/profile mismatch · status={frame.get('p')} · list={selected[0].label}"
                    )
                )
        elif not selected:
            profile_lines.append(report.warn("No profile has selected=true"))
        else:
            labels = ", ".join(p.label for p in selected[:3])
            profile_lines.append(report.error(f"Multiple selected profiles · {labels}"))

    report.section("Profiles", *profile_lines)

    # --------------------------------------------------------------- history
    history_lines: list[str] = []
    latest = None
    try:
        index = await asyncio.wait_for(client.fetch_index(), timeout=8.0)
        latest = _latest_history_entry(index)
    except Exception as exc:  # noqa: BLE001
        history_lines.append(report.error(f"History index failed · {type(exc).__name__}: {exc}"))
    else:
        active_count = sum(
            1
            for entry in index.entries
            if entry.completed and not entry.deleted
        )
        history_lines.append(report.ok(f"History index · {active_count} active shots"))
        history_lines.append(f"next_id {index.next_id}")

        processed = state.get("last_shot_id")
        if latest is None:
            history_lines.append(report.warn("No completed shots in GaggiMate history"))
        else:
            history_lines.append(f"Latest GaggiMate shot #{latest.id}")
            history_lines.append(f"Last MATEbot shot {('#' + str(processed)) if processed is not None else '—'}")
            if processed is None:
                history_lines.append(report.warn("MATEbot has no last_shot_id state yet"))
            else:
                try:
                    delta = latest.id - int(processed)
                except (TypeError, ValueError):
                    history_lines.append(report.error(f"Invalid MATEbot last_shot_id · {processed!r}"))
                else:
                    if delta == 0:
                        history_lines.append(report.ok("Shot IDs synchronized"))
                    elif delta > 0:
                        history_lines.append(
                            report.warn(f"MATEbot is {delta} shot(s) behind GaggiMate")
                        )
                    else:
                        history_lines.append(
                            report.warn(f"MATEbot state is {-delta} shot(s) ahead of GaggiMate history")
                        )

            try:
                notes = await asyncio.wait_for(client.fetch_notes(latest.id), timeout=5.0)
            except Exception as exc:  # noqa: BLE001
                history_lines.append(report.warn(f"Latest Shot Notes check failed · {exc}"))
            else:
                if notes is not None:
                    rating = notes.get("rating")
                    suffix = f" · rating {rating}/5" if rating is not None else ""
                    history_lines.append(report.ok(f"Latest Shot Notes present{suffix}"))
                elif latest.has_notes:
                    history_lines.append(report.warn("History says notes exist, but notes JSON was not readable"))
                else:
                    history_lines.append(report.warn("Latest shot has no Shot Notes"))

    report.section("History", *history_lines)
    return report
