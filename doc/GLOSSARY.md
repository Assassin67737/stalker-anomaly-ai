# VARKA — Glossary

> Single source of terminology for all public documentation.
> When a term appears in README / ARCHITECTURE / DESIGN / ROADMAP, its definition lives here.
> Terms from v0.11 are kept; where their meaning changed, an *(October)* note says how.
> Terms added later are in the last section. History of the ideas: [EVOLUTION.md](EVOLUTION.md).

---

## Core Concepts

**Protagonist Bias**
The industry-standard AI design choice where NPCs are tuned to lose to the player: accuracy is deliberately reduced, reaction times are inflated, memory is shortened. Makes games feel "fair" by making enemies dumb. VARKA rejects this entirely.

**Believability**
The design target of VARKA. Not "smarter AI" — believable AI. An NPC that behaves like a real person with real limitations. Believability comes from *plausible constraints*, not from computational power.

> *"Complex not smart."* — core design principle

**Honest Belief**
An NPC only knows what it could realistically know: what it has seen, heard, or inferred. No wall-hacks. No global omniscience. The system enforces this architecturally — it is not a handicap added on top of a cheating engine.

---

## Belief System

**Belief**
The NPC squad's current working hypothesis about where the enemy is. A lightweight data structure:
```
belief = { pos, bearing, stamp, cone_angle, mass }
```
Not a precise location — a *probability region* approximated by a geometric cone on the navmesh.

**LKP — Last Known Position**
The last position where the enemy was directly observed. The seed from which belief grows. As time passes without observation, belief *diffuses* outward from LKP.

**Bearing**
The inferred direction of enemy movement at the moment of last contact. Points *away from the observer* (the direction a rational actor would flee), not toward the last seen position. Used to bias the diffusion cone.

**Belief Cone**
The geometric region where the enemy *might* be. Defined by: origin (LKP), bearing, cone angle, and reach distance. Angle and reach grow over time — old belief is wide and uncertain; fresh belief is a tight spear.

**Belief Mass**
The second axis of belief, orthogonal to geometry. Geometry answers *where*; mass answers *how much to trust it*. Decays linearly from 1 (fresh) to 0 (forgotten). Objective property of the belief — all squad members share the same mass. Rank affects only the *threshold* at which a soldier stops acting on low-mass belief.

**Clinical Death** (of a belief)
When belief mass falls below a rank-dependent threshold, the soldier *stops acting on it* even though the belief object still exists. A veteran discards thin beliefs early; a rookie chases ghosts to the end.

**Biological Death** (of a belief)
When belief mass reaches exactly 0, the belief object is deleted from memory entirely.

**Diffusion**
The natural spreading of belief over time. The cone angle grows, reach extends, mass decays. The enemy *could be anywhere in the cone* — the system doesn't pretend to know more than it does.

**Notice**
An external event that plants or refreshes a belief from a non-visual source — a gunshot heard, a corpse found. Injects fresh belief at the event's location without requiring direct line of sight.

---

## Architecture Layers

**School A — Particle Belief** *(deferred)*
The theoretically correct approach: N particle hypotheses spreading from LKP, bouncing off walls. Equivalent to a particle filter / Monte Carlo Localization from robotics. Accurate, but cost = N × raycast × tick × squad. Dropped FPS in testing. Parked indefinitely.

**School B — Geometric Belief** *(chosen)*
The working approach. Belief = one lightweight cone object per squad. Walls are handled implicitly: the navmesh has *holes* where walls are — diffusion simply has no nodes there, so attention flows through doorways naturally. No raycasts. Emergent, not scripted.
*(October: still chosen. v1 is the cone; v2 is the wave — see Belief v2 below. "No raycasts" holds for belief,
not for decisions — see Eyes.)*

**Navmesh**
The 2D walkable surface baked into STALKER's maps. A "carpet" draped over 3D geometry. VARKA uses it as the belief space: if there's no navmesh node, a human can't stand there, so belief doesn't go there. Walls become *missing data*, not *forbidden zones*.

**Fan (веер)**
The technique for sampling navmesh nodes inside a cone: K rays fired via `level.vertex_in_direction()`. A wall = the ray doesn't advance = a hole in the data. No node list returned ≠ wall explicitly blocked — *absence of evidence* does the filtering.

**snap_to_mesh**
A correction applied when LKP lands off the navmesh (enemy on a crate, elevated surface, etc.). The LKP is pulled toward the nearest reachable navmesh node before the fan is cast, preventing the entire belief cone from going blind.

---

## NPC Properties

**Rank**
A scalar value encoding NPC experience: Novice → Trainee → Experienced → Professional → Veteran → Expert → Master → Legend. In VARKA, rank is a *continuous lever* that bends detection speed, belief thresholds, cover discipline, and reaction time. Not a discrete class with hardcoded behavior.

**is_rookie()**
Shorthand for rank < 6500 (Novice / Trainee). The boundary between panic-driven and tactical behavior.

---

## Combat Architecture

**Combat Layer** (звено)
One of four sequential engineering milestones for the full combat AI stack:
1. **Perception** — sight, hearing, memory ← *current*
2. **Danger** — reaction to grenades, corpses, suppression
3. **Cover** — smart positioning
4. **Coordination** — squad-level tactics (hard-gated until layers 1–3 are solid)

*(October: the sequence was dropped on 20.10; all four grow side by side. See Director, Hands.)*

**Consumer** (потребитель)
Any system that *reads* belief and acts on it. The belief core itself does not move NPCs — consumers do. Current consumers: `varka_search` (gaze sweep), `varka_alert` (gunshot/corpse channel).
*(October: consumers are now called hands — `varka_search_action`, `varka_clear`; `varka_search` is parked.)*

**Polygon** (полигон)
Internal term for a test scenario: a save with pre-spawned NPCs used to verify a specific behavior in-engine. Equivalent to a manual integration test.
*(October: still used for watching by eye; numbers come from Matches.)*

---

## Design Principles (preserved as-is)

> **"Complex not smart."**
> Believability from plausible constraints, not from computational power.

> **"Don't summon the monster too early."**
> Squad coordination is gated behind solid individual perception. No layer 4 before layers 1–3.
> *(October: retired on 20.10 — the director is the point of the mod. Its spirit lives on as "measure first".)*

> **"Visible wins over ambitious rewrites."**
> Four layers, one at a time. Incremental confirmed progress beats one large uncertain leap.
> *(October: "visible" now means seen by eye **and** confirmed by a series of matches.)*

> **"Data, not state."**
> Behavior is declared in logic configs, not hardcoded per-character.

---

## Terms added since v0.11

**Belief v2 (wave)**
`varka_belief`, 22.10. The squad's belief as mass on the navmesh that travels at a runner's speed (walls hold
it, corners are rounded), is erased by whatever any squad member sees, and flows back into ground nobody is
watching. The edge between checked and unchecked ground is a **gap** — the place worth watching.

**Hands** (руки)
Actions in an NPC's main GOAP planner that carry out a decision: search, peek, hold the edge, regroup, survive,
finish, evade a grenade, follow an order. They yield to vanilla combat when the enemy is in sight.

**Director** (дирижёр)
The squad-level mind: picks a preset and a play, tracks morale, assigns roles to hands. One recursive
"assignment" function meant to work at any scale (fighter → squad → several squads).

**Preset / Play**
A preset is a squad's style (e.g. front, bound). A play is what the preset does at contact: FRONT (a line across
the enemy's direction, a sector each), BOUNDING (two pairs: one fires, one moves), WITHDRAW (morale-driven).

**Morale / Wear**
Morale: the squad's belief that it will win — one number, rises for the winning side. Wear: how much threat of
death a fighter has absorbed — grows for everyone, fades only at rest, lengthens aim time and drags morale.

**Eyes**
Line-of-sight checks spent only at decision points (`varka_eyes`, about 0.3 ms per decision), plus a baked map
of what each navmesh node can see (`varka_vision`), verified against the engine's `ray_pick`.

**Fire gate** (ворота огня)
`varka_aim`: before a scripted pose pulls the trigger — turned toward the enemy? barrel clear crouched → fire
crouched; clear only standing → stand up over cover and fire; neither → hold fire.

**Match / Runner / Trace**
A match: two squads set on each other in the live game, ended by elimination or time, scored by `score.py`.
The runner (`tools/twin/match/run.py`) plays series of them. The trace (`varka_trace.jsonl`) logs every event.

**Pure vanilla squad**
A squad marked at spawn that every VARKA hook skips (`varka_vanilla`), for honest VARKA-vs-vanilla matches.

**Twin / Vessel** (двойник / сосуд)
A LuaJIT simulation of the same fights. The *vessel* is its body — bullets, anatomy, speeds, sight, wounds —
audited against the game's engine source and numbers. Its mind is a pluggable *brain*.

**Unfinished game** (недоигра)
The design stance for the twin: reproduce the game's body faithfully and leave decisions empty — a space of
opportunity for a learner, not a copy of vanilla's behaviour.

**Modded Exes**
The community build of the Anomaly engine (xray-monolith). VARKA needs it since v0.24 for hooks the stock exe
lacks (grenade throw decision and spawn callbacks, the `ai_aim_fire_angle` console variable).

