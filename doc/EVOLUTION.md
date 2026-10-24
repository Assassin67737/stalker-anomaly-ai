# VARKA — Evolution

> How the mod and its ideas changed, from the first public design (v0.11, July 2026) to now.
> Older documents are kept as they were written — this file says what each of them got right,
> what turned out differently, and why. Nothing is erased: the path is part of the design.

---

## The short version

| | July 2026 (v0.11) | October 2026 (v0.26) |
|---|---|---|
| **What VARKA is** | A belief layer: NPCs remember where the enemy probably went | A squad combat brain: belief, hands, fire, morale, a director — and a workbench to measure it |
| **Belief** | A cone with mass, sampled by a navmesh fan (`varka_lkp`) | A wave on the navmesh that eyes erase (`varka_belief`, belief v2); the cone still runs for search and telemetry |
| **Walls and sight** | "Zero raycasts" — walls are missing navmesh nodes | Rays where a decision needs them: on-demand eyes, the fire gate, a baked spatial-vision map checked against the engine to the triangle |
| **Order of work** | Four layers, strictly in sequence, coordination hard-gated | Gate lifted (20.10): the director is the point of the mod. Layers are built side by side and judged by measured fights |
| **How we know it works** | Watching a test fight by eye ("polygon") | By eye *and* by numbers: a match runner, telemetry of every shot/hit/death, night series of 100+ fights |
| **Where the code runs** | Stock Anomaly 1.5.3 exe | Modded Exes (community engine build) — needed for grenade and aim hooks |
| **The repository** | "Primarily a design document repository" | The mod, its tools (twin, match runner, viewers) and the design trail |
| **License** | MIT + CC BY 4.0 | GPL-3.0-or-later + CC BY-SA 4.0 — a community mod that stays open |

---

## Timeline

**July 2026 — the belief core (v0.1–v0.17).**
Memory buffer, rank-scaled detection, corpse and sound channels, the belief cone with mass, the gaze sweep,
the lot book (squad members claim different covers instead of all running to the same one), the search machine
with HOLD (watch the corner after the sweep). On 13.07 the mod was cut down to a "v1-core" to publish a verified
skeleton; the director went to a parking lot. 17.07: VARKA-TC, a structured trace of every belief event,
plus a top-down viewer to watch belief live.

**The honest finding of July:** the wanted behaviour (squad splits the area, acts uncertain) was seen once in all
tests. Not broken — not working. That pushed the next phase toward measurement instead of more mechanics.

**19–20 October — a bridge to the game and the director returns.**
A navmesh parser (`level.ai`), a map viewer, a creative mode (spawn / order / freeze from a browser panel),
a raycaster over the level's collision mesh whose hits match the engine's `ray_pick` triangle for triangle.
On 20.10 the gate was lifted: "the director is the main idea of the mod". Director v0.7: per-squad presets,
contact plays (FRONT, BOUNDING, WITHDRAW), morale v0.2, after-fight regroup, enemy weapon knowledge,
weapon choice by range. A match runner: spawn two squads, set them on each other, score the outcome.

**21 October — the crash.** Weeks of random crash dumps traced to one engine rule: a script action with a
custom id inside the C++ combat sub-planner sends the engine into a `switch` with no default when a killer
shouts "enemy down". Fix: our search lives under vanilla id 34, own actions only in the main planner.
Confirmed by a night of 128 matches without a single dump. The rule is now written down (`PLANNER_MAP.md`).

**21–23 October — hands, fire and survival.**
Telemetry of every shot (eye and muzzle line to the enemy), "wear" from the threat of death, belief v2
(the wave), peek / hold-the-edge hands with a corner ambush, "want to live" (turn to the shooter who hit me,
dash out of his sight), friendly-fire check by geometry (the vanilla check silenced 23% of the time a
fighter saw an enemy), renegades finishing the downed mid-fight, one executioner per victim.

**24–25 October — the vessel and honest comparison.**
The twin (a LuaJIT simulation of the same fights) was audited against the game, mechanic by mechanic,
from the engine source: bullet spread, multi-bone hits and anatomy, movement speeds, the wounded state,
materials, vision. It now reproduces the game's numbers (hit per shot 12.4% vs ~12%, wounded before death
23.1% vs 23.0%, median match 81 vs 78 s). Grenades v2 (real fuse, cooking by rank, skill error instead of
engine dice), a fire gate (no trigger pull while turned away or with the barrel against cover), and
"pure vanilla" squads so that VARKA can fight unmodified Anomaly in the same game.

---

## Ideas that changed

**"Zero raycasts" → rays on demand.**
The navmesh is still the space belief lives in. But sight is not walkability: windows, low walls and fences
see through where nobody can walk, and a corridor corner hides where the navmesh is continuous.
Rays are spent only at decision points (where to hold a corner, can the barrel reach the chest), and
whole-level sight is baked offline into a lookup map.

**The cone → the wave.**
The cone answered "where did he go" with a direction and a spread. Belief v2 is closer to the theory
(`THEORY.md` §2–3): mass travels at a runner's speed along the navmesh, what any squad member sees is erased,
the shadow flows back where nobody looks, and the edge between checked and unchecked ground becomes the
place to watch. It is still being judged by eye; whether "clouds" are the right picture at all is open.

**Layer gate → build and measure.**
"No layer 2 on an unconfirmed layer 1" protected debugging. In practice the decisive questions were about
fights, not perception, and they could only be answered with whole fights. The replacement for the gate is
measurement: every claim is a number from a series of matches, not a single good-looking fight.

**Rank as a lever — and what the engine actually does with it.**
Rank still bends curves, never branches code. But the audit found that the engine clamps rank before it
reaches weapon accuracy and rank immunity: every NPC fires with the same base dispersion whatever its rank.
Rank today works through what VARKA adds (detection speed, belief, grenade skill, wear, knowledge).
Next on this line: a statistical portrait of a fighter instead of a single rank number.

**Policy waits for perception → hands are part of the brain.**
v0.11 deliberately controlled only eyes and memory. Belief without feet changed nothing in a fight, so the
hands came: orders, search, peek and hold, regroup, survive, finish, grenades — all as actions in the main
planner that yield to vanilla combat when the enemy is in sight.

**The twin: from predictor to vessel.**
At first the twin was meant to predict the game. Now its role is narrower and stricter: reproduce the game's
body (bullets, damage, speeds, sight, wounds) faithfully and leave the decisions empty, so that a learner can
fill them and the result can be carried back into the game.

---

## Still open

- Does `set_enemy` restart the engine's 60 s forget timer? (open since v0.11)
- Is belief something players can *see* in a solo fight? The answer decides the shape of belief v3.
- The director's presets have not yet shown a measured gain over vanilla in the game; fire changes have,
  in the twin. The vanilla-vs-VARKA matches are the next test.
