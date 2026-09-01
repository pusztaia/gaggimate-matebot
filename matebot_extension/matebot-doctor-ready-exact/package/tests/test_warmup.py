from matebot.warmup import WarmupPhase, WarmupTracker


def frame(ct, tt=94.0, mode=1):
    return {"tp": "evt:status", "ct": ct, "tt": tt, "m": mode}


def test_crossing_target_does_not_mark_ready_without_overshoot():
    w = WarmupTracker()
    w.observe(frame(25.0), now=0)
    assert w.observe(frame(94.0), now=100).phase in {WarmupPhase.OBSERVING, WarmupPhase.HEATING}
    snap = w.observe(frame(94.1), now=130)
    assert not snap.ready
    assert not snap.overshoot_seen


def test_overshoot_then_settle_then_ready():
    w = WarmupTracker()
    assert w.observe(frame(25.0), now=0).phase == WarmupPhase.HEATING
    assert not w.observe(frame(94.0), now=100).ready
    over = w.observe(frame(99.7), now=150)
    assert over.phase == WarmupPhase.OVERSHOOT
    assert over.overshoot_seen
    settling = w.observe(frame(97.0), now=160)
    assert settling.phase == WarmupPhase.SETTLING
    band = w.observe(frame(94.5), now=170)
    assert band.phase == WarmupPhase.SETTLING
    assert band.stable_for_s == 0
    almost = w.observe(frame(94.4), now=189.9)
    assert not almost.ready
    ready = w.observe(frame(94.2), now=190.1)
    assert ready.phase == WarmupPhase.READY
    assert ready.ready
    assert ready.peak_c == 99.7
    # peak observed at now=150; band held from stable_since=170 for 20s -> 190
    assert ready.settle_duration_s == 40.0


def test_leaving_brew_resets_cycle():
    w = WarmupTracker()
    w.observe(frame(99.7), now=0)
    w.observe(frame(94.2), now=10)
    ready = w.observe(frame(94.1), now=31)
    assert ready.ready
    assert ready.settle_duration_s == 30.0
    idle = w.observe(frame(94.0, mode=0), now=32)
    assert idle.phase == WarmupPhase.IDLE
    assert not idle.ready
    assert not idle.overshoot_seen
    assert idle.settle_duration_s is None


def test_target_change_after_ready_requires_resettling_but_not_new_overshoot():
    w = WarmupTracker()
    w.observe(frame(99.7, 94.0), now=0)
    w.observe(frame(94.2, 94.0), now=10)
    first_ready = w.observe(frame(94.1, 94.0), now=31)
    assert first_ready.ready
    # peak at now=0; band held from stable_since=10 for 20s -> 30
    assert first_ready.settle_duration_s == 30.0

    changed = w.observe(frame(94.1, 93.0), now=32)
    assert not changed.ready
    assert changed.overshoot_seen
    assert changed.phase == WarmupPhase.SETTLING
    # the original cycle's settle duration is a fact about this brew, not
    # recomputed just because a later target change forces a re-settle
    assert changed.settle_duration_s == 30.0

    w.observe(frame(93.4, 93.0), now=40)
    ready_again = w.observe(frame(93.2, 93.0), now=61)
    assert ready_again.ready
    assert ready_again.settle_duration_s == 30.0


def test_first_brew_frame_near_target_is_observing_not_ready():
    w = WarmupTracker()
    snap = w.observe(frame(94.0), now=0)
    assert snap.phase == WarmupPhase.OBSERVING
    assert not snap.ready
