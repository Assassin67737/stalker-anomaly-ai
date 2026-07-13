# VARKA — Roadmap

> What is done, what is in progress, what is next.
> Versions correspond to git tags in the source repository.

---

## Combat Layer Stack

VARKA is built in four sequential layers. Each layer is validated in-engine before the
next begins. No layer 2 on unconfirmed layer 1.

```
Layer 1 — Perception    ← CURRENT
Layer 2 — Danger
Layer 3 — Cover
Layer 4 — Coordination  (hard-gated until 1–3 are solid)
```

---

## Layer 1 — Perception / Memory

**Goal:** NPCs remember where the enemy probably went. Memory is honest (only what
was seen/heard), persistent (survives line-of-sight breaks), and shared across the squad.

| Version | What | Status |
|---------|------|--------|
| v0.1 | Memory buffer: `still_visible_time` 0→800ms, danger 200→1500ms | ✅ Confirmed in-engine |
| v0.2 | Danger reaction to allied corpse (was written by devs, disabled) | ✅ |
| v0.3 | Detection speed × rank: Novice ×0.55, Legend ×1.90, delta ×3.4 | ✅ Confirmed visually |
| v0.4 | Voice alert on ally corpse → chain reaction via `hear_callback` | ✅ |
| v0.5 | Rookie corpse-danger behavior: hide and wait, not rush LKP | ✅ |
| v0.6 | Belief probe (read-only): cone visualization, navmesh fan, squad table | ✅ Both navmesh ⚠️ closed |
| v0.7 | Belief core: `snap_to_mesh`, public API, diffusion confirmed visually | ✅ 15×15 stress test passed |
| v0.8 | Consumer 1 — gaze sweep: contact loss → weapon-up fan sweep | ✅ `set_sight` override confirmed in engine combat |
| v0.9 | Bearing fix: inertia → escape direction | ✅ Diffusion confirmed, direction pending re-check |
| v0.10 | Belief mass: second axis, rank-based clinical threshold, cover-weighted sweep | ✅ Confirmed: thresholds 0.14 vs 0.08, ×11/×18 |
| v0.11 | Consumer 2 — audio + corpse channels, `set_enemy` flag restore | ⏳ Written, not yet validated |

**Remaining Layer 1 work:**
- Validate v0.11 in-engine (key question: does `set_enemy` reset the 60s engine timer?)
- If not: combat-ignore × rank (extend engine alert duration per rank)
- Opponent assessment multiplier ("rhino" — doesn't take cover under weak threats)

---

## Layer 2 — Danger

**Goal:** NPCs react to suppression, grenades, nearby deaths, and breaching in ways
that scale with rank and perceived threat.

Planned scope (not started):
- Suppression response × rank × threat assessment (Obs. 7.5)
- "Saw it, not yet firing" delay × rank (Obs. 7.7, 7.10)
- Threat priority: who gets focused when multiple enemies are active (Obs. 7.2)
- Alert mode duration tied to belief state, not only engine timer (Obs. 7.9)

---

## Layer 3 — Cover

**Goal:** NPCs choose cover positions relative to *where they think the enemy is*,
not relative to hardcoded map points.

Planned scope (not started):
- Belief-based cover selection: `npc:find_best_cover(belief.pos)` (uses navmesh cover data)
- Fix texture-shooting from smart_cover positions (Obs. 7.1)
- Break job determinism: position as function of belief, not static priority queue (Obs. 7.3)

---

## Layer 4 — Coordination

**Hard-gated.** Not planned until layers 1–3 are validated.

Designed architecture (parked, no code):
- Squad level: market-based task allocation (bid = geodesic cost + rank + weapon + hysteresis)
- Soldier level: utility AI (IAUS / Dave Mark) — roles as argmax over scored considerations
- Rank-differential determines roles emergently: steep spread → commander-with-meat; flat spread → all-tanks

---

## Deferred Ideas

These are architecturally sound but require the core layers to be in place first:

- **Simulated weapon** — aim vector with inertia, recoil, skill-based recovery. Miss = weapon state, not `if random()`. Closer to Layer 2–3.
- **Morale axis** — fear/resolve as a continuous state variable, not a constant. Grows out of suppression (Layer 2) and death events. Requested during testing.
- **Memory of place** — timestamps on navmesh nodes ("checked this doorway 4s ago") → methodical room clearing. Extends Layer 1 belief into spatial memory.
- **GAMMA portability** — adapting VARKA to the GAMMA modpack (separate engine environment, different baseline scripts). After base validation.
- **School A (particle belief)** — the theoretically correct model. Parked: cost is prohibitive on the X-Ray engine. Remains the right answer for a custom engine.
