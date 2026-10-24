# VARKA — Roadmap

> What is done, what is in progress, what is next.
> Versions correspond to commits in this repository.

---

## Where we are (October 2026, v0.26)

| Version | Date | What |
|---------|------|------|
| v0.12–v0.17 | July | Lot book (covers claimed per squad), search machine: gaze + feet + HOLD (watch the corner) |
| v0.18 | 19.10 | HOLD with on-demand eyes; watchdog becomes a pure assert |
| v0.19–v0.22 | 20.10 | Director revived (presets, contact plays, morale v0.2, regroup), creative mode, spatial vision, match runner |
| v0.23 | 21.10 | **Crash found and fixed** (custom ids in the combat sub-planner); verified: 128 night matches, 0 dumps |
| v0.24 | 21.10 | Shot telemetry, wear from threat of death; move to Modded Exes |
| v0.25 | 23.10 | Belief v2 (wave) + peek / hold-edge hands, "want to live", friendly-fire by geometry, one grenade per squad |
| v0.26 | 25.10 | Twin audited against the game; fire gate; grenades v2; pure-vanilla squads; GPL-3.0 |

**Next, in order:**
1. **VARKA vs pure vanilla in the game** — identical squads, a series of matches (`matches/vanilla_vs_varka.json`).
2. **Watch the fresh parts by eye** — fire gate, grenades v2 without prone, belief v2 hands.
3. **A learner in the twin** — start from an empty mind on the audited body, bound only the blatant exploits,
   and carry what it finds back as a benchmark; ranks get a share of it.
4. **Belief v3** — something a player can *see* in a solo fight against a squad (the "cloud" picture is in doubt).
5. Later: a fighter's statistical portrait instead of rank, GAMMA compatibility (it replaces `xr_danger` and
   `visual_memory_manager` too), quadrant / area conductor (parked after a night without gain).

---

# Roadmap as of v0.11 (July 2026)

*Kept as written. Notes in italics say what became of each part.*

## Combat Layer Stack

VARKA is built in four sequential layers. Each layer is validated in-engine before the
next begins. No layer 2 on unconfirmed layer 1.

```
Layer 1 — Perception    ← CURRENT
Layer 2 — Danger
Layer 3 — Cover
Layer 4 — Coordination  (hard-gated until 1–3 are solid)
```

*October: the sequence did not survive contact with fights. The gate was lifted on 20.10 and the layers grew
side by side, kept honest by measurement instead.*

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

*October: v0.11 channels shipped; `set_enemy` vs the 60 s timer is still unverified. Belief went on to v2.*

---

## Layer 2 — Danger

**Goal:** NPCs react to suppression, grenades, nearby deaths, and breaching in ways
that scale with rank and perceived threat.

Planned scope (not started):
- Suppression response × rank × threat assessment (Obs. 7.5)
- "Saw it, not yet firing" delay × rank (Obs. 7.7, 7.10)
- Threat priority: who gets focused when multiple enemies are active (Obs. 7.2)
- Alert mode duration tied to belief state, not only engine timer (Obs. 7.9)

*October: partly done in other shapes — "want to live" (turn to the shooter who hit me, dash out of sight),
grenades v2 (see it → shout and sprint), wear from threat of death feeding aim time and morale.*

---

## Layer 3 — Cover

**Goal:** NPCs choose cover positions relative to *where they think the enemy is*,
not relative to hardcoded map points.

Planned scope (not started):
- Belief-based cover selection: `npc:find_best_cover(belief.pos)` (uses navmesh cover data)
- Fix texture-shooting from smart_cover positions (Obs. 7.1)
- Break job determinism: position as function of belief, not static priority queue (Obs. 7.3)

*October: cover is chosen by the fire gate's two-ray rule (crouch if the barrel clears, stand if only
standing clears, else don't fire) inside vanilla's fight-from-cover; peek / hold-edge pick ambush points from
belief v2.*

---

## Layer 4 — Coordination

**Hard-gated.** Not planned until layers 1–3 are validated.

Designed architecture (parked, no code):
- Squad level: market-based task allocation (bid = geodesic cost + rank + weapon + hysteresis)
- Soldier level: utility AI (IAUS / Dave Mark) — roles as argmax over scored considerations
- Rank-differential determines roles emergently: steep spread → commander-with-meat; flat spread → all-tanks

*October: built in a simpler form — per-squad presets and contact plays (front line, bounding) driven by
morale. No measured gain over vanilla yet; a learner may replace hand-written presets.*

---

## Deferred Ideas

These are architecturally sound but require the core layers to be in place first:

- **Simulated weapon** — aim vector with inertia, recoil, skill-based recovery. Miss = weapon state, not `if random()`. Closer to Layer 2–3.
- **Morale axis** — fear/resolve as a continuous state variable, not a constant. Grows out of suppression (Layer 2) and death events. Requested during testing.
- **Memory of place** — timestamps on navmesh nodes ("checked this doorway 4s ago") → methodical room clearing. Extends Layer 1 belief into spatial memory.
- **GAMMA portability** — adapting VARKA to the GAMMA modpack (separate engine environment, different baseline scripts). After base validation.
- **School A (particle belief)** — the theoretically correct model. Parked: cost is prohibitive on the X-Ray engine. Remains the right answer for a custom engine.

*October: morale became real (director morale v0.2 + wear); GAMMA portability is on the list; memory of place
lives on as "checked" ground in belief v2.*
