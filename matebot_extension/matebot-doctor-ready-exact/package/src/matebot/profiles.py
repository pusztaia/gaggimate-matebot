"""Safe, read/select-only GaggiMate profile control.

The service is messenger-agnostic. Telegram and Discord can both render the
returned :class:`~matebot.messengers.base.Option` values through the existing
MATEbot messenger abstraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .machine import GaggiMateClient, MachineError


class ProfileError(RuntimeError):
    """Base class for profile-control failures."""


class ProfileNotFound(ProfileError):
    """The selected profile disappeared or no longer exists."""


class ProfileSelectionBlocked(ProfileError):
    """The requested profile is deliberately unavailable to normal control."""


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    id: str
    label: str
    type: str
    description: str
    favorite: bool
    selected: bool
    utility: bool
    temperature: float | None
    phase_count: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ProfileSummary":
        if not payload.get("id"):
            raise ProfileError("profile payload has no id")
        profile_id = str(payload["id"])
        raw_temp = payload.get("temperature")
        try:
            temperature = float(raw_temp) if raw_temp is not None else None
        except (TypeError, ValueError):
            temperature = None
        phases = payload.get("phases")
        return cls(
            id=profile_id,
            label=str(payload.get("label") or profile_id),
            type=str(payload.get("type") or ""),
            description=str(payload.get("description") or ""),
            favorite=bool(payload.get("favorite", False)),
            selected=bool(payload.get("selected", False)),
            utility=bool(payload.get("utility", False)),
            temperature=temperature,
            phase_count=len(phases) if isinstance(phases, list) else 0,
        )


@dataclass(frozen=True, slots=True)
class ProfilePage:
    items: tuple[ProfileSummary, ...]
    page: int
    pages: int
    total: int

    @property
    def has_previous(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return self.page + 1 < self.pages


def sort_profiles(profiles: Sequence[ProfileSummary]) -> list[ProfileSummary]:
    """Selected first, then favorites, then label."""
    return sorted(
        profiles,
        key=lambda profile: (
            not profile.selected,
            not profile.favorite,
            profile.label.casefold(),
            profile.id,
        ),
    )


def paginate_profiles(
    profiles: Sequence[ProfileSummary],
    *,
    page: int = 0,
    page_size: int = 6,
) -> ProfilePage:
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    total = len(profiles)
    pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(max(page, 0), pages - 1)
    start = safe_page * page_size
    return ProfilePage(
        items=tuple(profiles[start : start + page_size]),
        page=safe_page,
        pages=pages,
        total=total,
    )


class ProfileService:
    """Read/select profiles while keeping destructive APIs out of scope."""

    def __init__(self, client: GaggiMateClient) -> None:
        self.client = client

    async def list(
        self,
        *,
        favorites_only: bool = True,
        include_utility: bool = False,
    ) -> list[ProfileSummary]:
        payloads = await self.client.profiles_list()
        profiles = [ProfileSummary.from_payload(payload) for payload in payloads]
        if not include_utility:
            profiles = [profile for profile in profiles if not profile.utility]
        if favorites_only:
            profiles = [profile for profile in profiles if profile.favorite]
        return sort_profiles(profiles)

    async def current(self) -> ProfileSummary | None:
        profiles = await self.list(favorites_only=False, include_utility=True)
        return next((profile for profile in profiles if profile.selected), None)

    async def load(self, profile_id: str) -> dict[str, Any]:
        try:
            return await self.client.profile_load(profile_id)
        except MachineError as exc:
            if "not found" in str(exc).casefold():
                raise ProfileNotFound(profile_id) from exc
            raise

    async def select(
        self,
        profile_id: str,
        *,
        allow_utility: bool = False,
    ) -> ProfileSummary:
        profiles = await self.list(favorites_only=False, include_utility=True)
        target = next((profile for profile in profiles if profile.id == profile_id), None)
        if target is None:
            raise ProfileNotFound(profile_id)
        if target.utility and not allow_utility:
            raise ProfileSelectionBlocked(
                f"utility profile cannot be selected here: {target.label}"
            )

        await self.client.profile_select(profile_id)

        # Refresh from the machine. Never mark a profile selected before the
        # firmware acknowledges the request.
        refreshed = await self.list(favorites_only=False, include_utility=True)
        return next(
            (profile for profile in refreshed if profile.id == profile_id),
            target,
        )


def encode_callback(action: str, value: str = "") -> str:
    """Compact id that fits Telegram's 64-byte callback_data limit."""
    data = f"pf|{action}" + (f"|{value}" if value else "")
    if len(data.encode()) > 64:
        raise ValueError("profile callback id exceeds 64 bytes")
    return data


def decode_callback(data: str) -> tuple[str, str]:
    parts = data.split("|", 2)
    if len(parts) < 2 or parts[0] != "pf":
        raise ValueError("not a profile callback")
    return parts[1], parts[2] if len(parts) == 3 else ""


def format_current(profile: ProfileSummary | None) -> str:
    if profile is None:
        return "☕ Current profile\n\nNo selected profile reported by GaggiMate."
    temp = f"{profile.temperature:.1f} °C" if profile.temperature is not None else "—"
    favorite = "⭐" if profile.favorite else "No"
    utility = "Yes" if profile.utility else "No"
    return (
        "☕ Current profile\n\n"
        f"{profile.label}\n\n"
        f"Type: {profile.type or '—'}\n"
        f"Temperature: {temp}\n"
        f"Phases: {profile.phase_count}\n"
        f"Favorite: {favorite}\n"
        f"Utility: {utility}"
    )


def format_detail(payload: Mapping[str, Any]) -> str:
    profile = ProfileSummary.from_payload(payload)
    text = format_current(profile).replace("☕ Current profile", "☕ Profile details", 1)
    if profile.description:
        text += f"\n\n{profile.description}"
    phases = payload.get("phases") or []
    if phases:
        text += "\n\nPhases"
        for i, phase in enumerate(phases[:8], 1):
            name = phase.get("name") or phase.get("phase") or f"Phase {i}"
            duration = phase.get("duration")
            suffix = f" — {duration:g}s" if isinstance(duration, (int, float)) else ""
            text += f"\n{i}. {name}{suffix}"
        if len(phases) > 8:
            text += f"\n… and {len(phases) - 8} more"
    return text
