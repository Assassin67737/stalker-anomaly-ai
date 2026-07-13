# VARKA — Glossary

> Single source of terminology for all public documentation.
> When a term appears in README / ARCHITECTURE / DESIGN / ROADMAP, its definition lives here.

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

**Consumer** (потребитель)
Any system that *reads* belief and acts on it. The belief core itself does not move NPCs — consumers do. Current consumers: `varka_search` (gaze sweep), `varka_alert` (gunshot/corpse channel).

**Polygon** (полигон)
Internal term for a test scenario: a save with pre-spawned NPCs used to verify a specific behavior in-engine. Equivalent to a manual integration test.

---

## Design Principles (preserved as-is)

> **"Complex not smart."**
> Believability from plausible constraints, not from computational power.

> **"Don't summon the monster too early."**
> Squad coordination is gated behind solid individual perception. No layer 4 before layers 1–3.

> **"Visible wins over ambitious rewrites."**
> Four layers, one at a time. Incremental confirmed progress beats one large uncertain leap.

> **"Data, not state."**
> Behavior is declared in logic configs, not hardcoded per-character.
