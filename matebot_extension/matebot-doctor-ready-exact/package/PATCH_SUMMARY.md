# Patch summary

Exact target source: **MATEbot 0.4.0**, collected from the running container.

## Added commands

```text
/profile
/profiles
/profiles all
```

## Telegram / Discord UI

The existing generic `Option` abstraction is reused, so profile buttons are not
implemented as a Telegram-only fork. Telegram displays them as inline buttons;
Discord can render the same options through its existing button view.

## GaggiMate API calls

```text
req:profiles:list
req:profiles:load
req:profiles:select
```

No save/delete/reorder or remote brew-start operation is added.

## Safety

- utility profiles are hidden from normal menus;
- utility selection is rejected by the service;
- profile changes are blocked while a brew process is active;
- selection state is refreshed from GaggiMate after acknowledgement;
- callback IDs remain within the messenger 64-byte limit.

## Verification

```text
python compile: PASS
git apply on exact collected baseline: PASS
pytest: 9 passed
```
