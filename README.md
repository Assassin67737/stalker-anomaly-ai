# VARKA — Honest Combat AI for S.T.A.L.K.E.R. Anomaly

> *"Complex not smart."*

> **Status: alpha, work in progress (v0.26, October 2026).** This is a living workbench, not a release.
> Parts are verified in game (belief + search, crash-free over 128 night matches as of v0.23), parts are
> fresh and untested — every commit message says which. Targets Anomaly 1.5.3 with Modded Exes.
> Some sections below describe the original v0.11 design and are being rewritten.
> Ideas, bug reports and fights you recorded are welcome in Issues.

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

### How it grew (July → October 2026)

The paragraphs above are the original v0.11 pitch, and the belief cone still runs (`varka_lkp`).
Since then VARKA became a squad combat brain built around it:

- **Belief v2** — a wave on the navmesh: mass moves at a runner's speed, what any squad member sees is
  erased, the shadow flows back where nobody looks (`varka_belief`). **Hands** act on it: peek, hold the
  edge, ambush at the corner (`varka_clear`), search and watch (`varka_search_action`).
- **Fire and survival** — a fire gate (no trigger pull while turned away or with the barrel against cover),
  turning to the shooter who hit you, dashing out of his sight, friendly-fire check by geometry,
  grenades with a real fuse and cooking by rank.
- **The director** — per-squad presets and contact plays (front line, bounding), morale, wear from the
  threat of death, after-fight regroup, knowledge of the enemy's weapons.
- **A workbench** — a match runner that sets squads on each other in the live game and scores the outcome,
  telemetry of every shot, hit and death, and a twin (a fast simulation of the same fights, audited against
  the game's engine source) for experiments the game is too slow for.

What changed in the ideas themselves, and why, is in [doc/EVOLUTION.md](doc/EVOLUTION.md).

---

## What This Repository Contains

*(v0.11 described this as "primarily a design document repository". It is now the mod, its tools and the
design trail.)*

| Path | Contents |
|------|----------|
| [doc/EVOLUTION.md](doc/EVOLUTION.md) | How VARKA changed from v0.11 to now — **start here** |
| [doc/GLOSSARY.md](doc/GLOSSARY.md) | Terms |
| [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) | How it is built (current map on top, v0.11 design below) |
| [doc/DESIGN.md](doc/DESIGN.md) | Why each choice was made, and which ones were revised |
| [doc/THEORY.md](doc/THEORY.md) | Mathematical basis: recursive Bayes, geodesic front, infotaxis *(Russian)* |
| [doc/ROADMAP.md](doc/ROADMAP.md) | Where we are and what is next |
| [doc/PLANNER_MAP.md](doc/PLANNER_MAP.md) | Vanilla NPC planner vs VARKA: what is ours, the crash rule *(Russian)* |
| [doc/VESSEL_AUDIT.md](doc/VESSEL_AUDIT.md) | The twin checked against the game, mechanic by mechanic *(Russian)* |
| [doc/LEARNING.md](doc/LEARNING.md) | Plan for training the director *(Russian)* |
| [doc/vanilla_ai_map/](doc/vanilla_ai_map/) | How vanilla Anomaly AI works, one NPC to scenarios *(Russian)* |
| `src/` | The mod: `gamedata/scripts` + `gamedata/configs` |
| `tools/twin/` | Map/vision bakers, viewers, creative mode server, match runner, the twin simulation |
| `tools/constructor/` | Director "constructor": grammar of squad orders |
| `parked/` | Scripts that once ran and are no longer installed |

**The mod, by role** (`src/`):

| Role | Scripts |
|------|---------|
| Perception | `visual_memory_manager` (detection × rank), `configs/creatures/m_stalker.ltx`, `xr_danger` (corpse channel) |
| Belief | `varka_lkp` (v1 cone, echoes, telemetry of positions), `varka_belief` (v2 wave), `varka_alert` (sound and corpse → belief), `varka_intel` (enemy weapons) |
| Hands | `varka_search_action` (search + watch under vanilla id 34), `varka_clear` (peek / hold the edge), `varka_regroup`, `varka_survive`, `varka_finish`, `varka_grenade`, `varka_lots` |
| Fire | `varka_aim` (fire gate) + `axr_fight_from_cover`, `rx_ff` (friendly in line), `varka_weapons` (weapon by range), `xrs_kill_wounded`, `varka_stress` (wear → aim time) |
| Director | `varka_director` (presets, morale), `varka_plays` (front, bounding, withdraw) |
| Eyes | `varka_eyes` (rays on demand), `varka_vision` (baked spatial vision) |
| Workbench | `varka_cmd` (orders, creative mode), `varka_match`, `varka_trace`, `varka_vanilla` (pure-vanilla squads), `varka_hud`, `varka_probe`, `varka_watchdog` |

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

**Revised since v0.11** (details in [doc/EVOLUTION.md](doc/EVOLUTION.md)):
- *Zero raycasts* → rays where a decision needs them (holding a corner, can the barrel reach), and
  whole-level sight baked offline. The navmesh is still where belief lives.
- *The cone* → a wave (belief v2), closer to the theory; the cone still drives search and telemetry.
- *Rank* still bends curves — but the engine turned out to clamp rank before weapon accuracy, so every
  vanilla NPC shoots with the same base spread. Rank works through what VARKA adds.
- *Perception first, policy later* → hands and a director, judged by measured fights instead of a layer gate.

---

## Platform

- **Game:** S.T.A.L.K.E.R. Anomaly 1.5.3 (standalone, free)
- **Engine:** X-Ray (2007) with [Modded Exes](https://github.com/themrdemonized/xray-monolith) —
  the community engine build (needed since v0.24 for grenade and aim hooks the stock exe lacks;
  v0.23 and earlier ran on the stock exe)
- **Language:** Lua — no C++ of our own, no engine recompile required
- **OS tested:** Arch Linux + Proton (game), native Lua tooling

## Installation

1. Install a clean copy of [S.T.A.L.K.E.R. Anomaly 1.5.3](https://www.moddb.com/mods/stalker-anomaly)
   and [Modded Exes](https://github.com/themrdemonized/xray-monolith).
2. Copy all `src/*.script` files into `<Anomaly root>/gamedata/scripts/`. Some of them replace vanilla
   files (`xr_danger`, `visual_memory_manager`, `rx_ff`, `axr_fight_from_cover`, `xrs_kill_wounded`) —
   other mods that replace the same files will conflict (GAMMA does, for `xr_danger` and
   `visual_memory_manager`).
3. Copy the `src/varka/` folder into `<Anomaly root>/gamedata/scripts/` (Lua modules loaded with `require`).
4. Copy `src/configs/` into `<Anomaly root>/gamedata/configs/` (merge, do not replace).
5. Launch the game. No save required — works on any new game or existing save.
6. Optional, for watching and measuring: `tools/twin/server.py` (viewer and creative mode) and
   `tools/twin/match/run.py` (matches) — see the docstrings at the top of each.

Test cycle: edit script → Alt+Tab → `F9` (quick load, for `.ltx` changes) or full restart
(for `.script` changes) → check `appdata/logs/xray_<user>.log` for Lua errors first.

---

## Status

**October 2026 (v0.26).** Verified in game: belief v1 and search, crash-free over a night of 128 matches
(v0.23). Measured: the friendly-fire fix (fire blocked 23% → 9% of the time an enemy is in sight).
In the twin, VARKA's fire changes beat vanilla squads clearly; the director's presets have not yet shown a
measured gain in the game. Fresh and not yet watched in game: belief v2 hands, fire gate, grenades v2,
pure-vanilla squads. Next: matches VARKA vs pure vanilla in the same game, then a learner in the twin.
See [doc/ROADMAP.md](doc/ROADMAP.md).

*At v0.11 (July 2026) this section read:* "Layer 1 (Perception) is ~90% validated. The belief core,
gaze sweep, and non-visual channels are implemented and tested in-engine. The director and flanker role
are written and under active validation."

This is active development, not a finished mod.

---

## Code by other authors

VARKA carries other people's work under their own names. It is copied as is, not "inspired by".

| Author | Work | What VARKA carries | License |
|--------|------|--------------------|---------|
| **bellyillish** | [Useful Idiots](https://github.com/bellyillish/useful-idiots) — companion overhaul for Anomaly and GAMMA | `src/varka/illish/lib/` — `pos` (cover height by six rays, open/enclosed/cramped space by sixteen rays, node claiming), `ray`, `vector`, `util`, `table`; verbatim from v1.4.10, only `require` paths changed | The Unlicense |

`git log --author=bellyillish` shows their commit; `git blame` on these files shows their lines.

---

## License

VARKA is a community mod: take it, change it, share it — and keep what you build from it just as open.

- The VARKA scripts (`varka_*.script`) are original work under **GPL-3.0-or-later** (`LICENSE`; summary of all terms — `LICENSING.md`).
- The tools (`tools/`: twin, constructor, match runner, viewers; not the baked level data) are **AGPL-3.0-or-later**
  (`tools/LICENSE`): running a modified copy as a server or web service means giving its users the source too.
- The design documents are **CC BY-SA 4.0** (`LICENSE-DOCS`): copy, translate and rework them, credit the source,
  and release what you make from them under CC BY-SA 4.0 too.
- Modified vanilla files and the level data baked from the game (`tools/twin/levels/`) retain the licensing of the
  Anomaly project.
- Code by other authors keeps its own license and its author's name (see above).
- Contributions keep their author's copyright and come in under the same terms, signed off with the DCO, with no CLA
  (`CONTRIBUTING.md`).

**Nothing released under these terms can be closed.** Not the code, not the design documents. Anyone may use
VARKA, commercial projects included, but whatever is built from it — a fork, a port to another engine, a
reworked design document — must be published under the same license, with its source, and with no extra
restrictions: no proprietary license, no NDA, no DRM (GPL-3.0 §5, §10; CC BY-SA 4.0 §3(b)). Running the tools
behind a server does not get around this (AGPL-3.0 §13).

Releases up to and including v0.25 were MIT / CC BY 4.0, and those copies stay under those terms. Everything
published from v0.26 (25.10.2026) on is GPL-3.0-or-later / CC BY-SA 4.0 only; `tools/` is AGPL-3.0-or-later
from 26.10.2026.
