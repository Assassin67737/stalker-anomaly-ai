# VARKA — Honest Combat AI for S.T.A.L.K.E.R. Anomaly

> *"Complex not smart."*

---

## The Problem

Every major game AI system, including STALKER's, is built around the same unspoken rule:
the player must feel like the protagonist. Enemies miss on purpose. They forget on purpose.
They react slowly on purpose.

This is a reasonable commercial decision. The player experience is smooth, failures feel
fair, and reviews are good.

It makes every enemy fundamentally dishonest.

VARKA removes that assumption. The Zone is an ecosystem with its own rules.
The player is a participant, not the VIP the rules were written for.

---

## What VARKA Does

VARKA adds a **persistent honest belief layer** to NPC squads.

When an NPC loses sight of the player, they don't forget. They form a working hypothesis:
*where did the enemy probably go?* That hypothesis diffuses over time, is shared with
squad members, and is updated by sound (a gunshot heard nearby) and evidence (a dead
ally found on the ground).

The core technical idea: instead of *where the enemy is*, the squad tracks *a geometric
region where the enemy might be*, which grows larger and less trusted as time passes.

```
Fresh contact   →  tight cone, high mass  →  "they went right, I'm sure"
30s since seen  →  wide cone, low mass   →  "somewhere in that building, maybe"
60s, no updates →  belief dies            →  "I've lost them"
```

This alone closes most of the trivial exploits: kill → hide → wait → repeat no longer
works because the act of killing is itself an information event that refreshes belief.

---

## What This Repository Contains

This is primarily a **design document repository**. The architecture is the contribution;
the Lua implementation is a reference that proves the design is viable on a real 2007 engine.

| Document | Contents |
|----------|----------|
| [doc/GLOSSARY.md](doc/GLOSSARY.md) | All terms defined precisely — start here |
| [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) | How the belief system is built |
| [doc/DESIGN.md](doc/DESIGN.md) | Why each architectural choice was made |
| [doc/THEORY.md](doc/THEORY.md) | Mathematical basis: recursive Bayes, geodesic front, infotaxis *(Russian)* |
| [doc/ROADMAP.md](doc/ROADMAP.md) | What is done, what is next |
| `src/varka_lkp.script` | Belief core: storage, update, diffusion, mass, fan |
| `src/varka_search.script` | Consumer 1: gaze sweep across fan nodes on contact loss |
| `src/varka_alert.script` | Consumer 2: audio + corpse channels → notice() + set_enemy() |
| `src/varka_director.script` | Director: assigns combat presets (ASSAULT, flanker) to squads |
| `src/varka_lots.script` | Lots: GOAP action definitions for each combat role |
| `src/varka_search_action.script` | Flanker action: picks a lateral node and runs to it |
| `src/varka_windows.script` | On-demand firing-line primitives (ray_pick over navmesh) |
| `src/varka_watchdog.script` | Error monitor: catches Lua errors mid-session |
| `src/varka_baker.script` | Research tool: navmesh bake probe (not required for the mod) |
| `src/visual_memory_manager.script` | Patched vanilla: detection speed × rank |
| `src/xr_danger.script` | Patched vanilla: danger reactions, corpse channel support |

---

## Key Design Choices (short version)

**Geometric belief, not particle filter.**
Theoretically, a particle filter (School A) is the correct model. It was rejected:
cost = N particles × raycast × tick × squad. A 2007 engine cannot afford it.
The geometric cone (School B) is a known approximation of the correct model, cheap
enough to run on every NPC in a large firefight.

**Navmesh as belief space, not raycasts.**
Walls are not checked with physics raycasts. Instead, the navmesh has *missing data*
where walls are — belief simply has no nodes to flow into. Attention flows through
doorways because doorways have nodes. Emergent occlusion, zero raycasts.

**Mass as a second axis.**
Geometry answers *where*. Mass answers *how much to trust it*. Decays with time.
Rank shifts the threshold: a veteran stops chasing low-mass belief early; a rookie
chases ghosts to the end. Same code, different thresholds.

**Rank as a continuous lever, not a behavior branch.**
No `if rank == "master" then`. Rank is a scalar that bends detection curves, belief
thresholds, and reaction multipliers. One code path, every NPC on a different part
of the curve.

---

## Platform

- **Game:** S.T.A.L.K.E.R. Anomaly 1.5.3 (standalone, free)
- **Engine:** X-Ray (2007), Lua / LuaJIT scripting layer
- **Language:** Lua — no C++, no engine recompile required
- **OS tested:** Arch Linux + Proton (game), native Lua tooling

## Installation

1. Install a clean copy of [S.T.A.L.K.E.R. Anomaly 1.5.3](https://www.moddb.com/mods/stalker-anomaly)
2. Copy all `src/*.script` files into `<Anomaly root>/gamedata/scripts/`
3. Copy `src/configs/` into `<Anomaly root>/gamedata/configs/` (merge, do not replace)
4. Launch the game. No save required — works on any new game or existing save.

Test cycle: edit script → Alt+Tab → `F9` (quick load, for `.ltx` changes) or full restart
(for `.script` changes) → check `appdata/logs/xray_<user>.log` for Lua errors first.

---

## Status

Layer 1 (Perception) is ~90% validated. The belief core, gaze sweep, and non-visual
channels are implemented and tested in-engine. The director and flanker role are written
and under active validation. See [doc/ROADMAP.md](doc/ROADMAP.md) for the current
validation state and what comes next.

This is active development, not a finished mod.

---

## License

VARKA is a community mod: take it, change it, share it — and keep what you build from it just as open.

- The VARKA scripts (`varka_*.script`) are original work under **GPL-3.0-or-later** (`LICENSE`; summary of all terms — `LICENSING.md`).
- The design documents are **CC BY-SA 4.0** (`LICENSE-DOCS`): take the ideas, credit the source, share alike.
- Modified vanilla scripts retain the licensing of the Anomaly project.

Releases up to v0.25 were MIT / CC BY 4.0 and remain so; later versions use the terms above.
