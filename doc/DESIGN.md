# VARKA — Design Decisions

> The *why* behind every architectural choice.
> For *what* was built, see [ARCHITECTURE.md](ARCHITECTURE.md).
> Written for v0.11 (July 2026). Decisions that were later revised carry a **Revised** note in place;
> decisions added since are at the end. The story of the changes: [EVOLUTION.md](EVOLUTION.md).

---

## Why This Exists

STALKER's combat AI has one structural defect: the player is not a participant in an
ecosystem — they are a protagonist whom the ecosystem exists to serve. NPCs forget
instantly, react slowly, and are quietly tuned to lose.

This is intentional in commercial games (readability, fairness, review scores). It is
*not* a constraint for a personal mod where the goal is the opposite: make the Zone
feel like a place with its own rules, not a theme park with one VIP guest.

**The design target is not "harder AI". It is honest AI.**
An NPC should know only what it could realistically know. Its decisions should follow
from that knowledge, not from a difficulty slider.

---

## Why Geometric Belief (School B), Not Particle Belief (School A)

School A (particle filter / MCL) is the theoretically correct model. N hypotheses,
each a point in space, spread from LKP and bounce off geometry. The output is a
genuine probability distribution over the map.

It was rejected for one reason: **cost is multiplicative**.

```
N particles × raycast × tick × squad members = the one expensive thing (raycasts),
multiplied by every factor at once
```

STALKER runs on a 2007 engine with a tight Lua budget. A 15-vs-15 engagement would
require hundreds of raycasts per tick just for belief geometry — before any actual
combat logic runs.

School B trades theoretical correctness for practical viability:

```
Geometric belief (cone) ≈ a coarse histogram filter on the navmesh
Cost: K navmesh lookups (cheap) × one object per squad (not per NPC)
```

The approximation has two known error terms (see ARCHITECTURE.md §Fan Technique).
Both are documented, bounded, and acceptable for the goal.

> **Revised (October 2026).** School B stayed — no particles. But belief v2 (`varka_belief`) moved from the
> cone to a wave on the navmesh with erasure by sight, which is the cheap form of the theory's geodesic front
> and negative update (THEORY.md §2–3) rather than a cone around it. Cost stays per squad, not per NPC.

---

## Why Navmesh Instead of Raycasts for Occlusion

The standard approach to "can belief spread through this wall?" is a raycast: fire a
ray, check if it hits geometry.

VARKA does not do this. Instead, walls are handled by the navmesh as *missing data*.

This is both cheaper and, for human movement prediction, more correct:

1. **Cost:** a navmesh lookup (`vertex_in_direction`) is ~100× cheaper than a physics raycast.
2. **Correctness:** humans can only stand where the navmesh exists. A wall has no navmesh nodes — not because it is "forbidden", but because there is nowhere to stand. The belief model *correctly* represents the enemy as being somewhere a human *can be*.

The result: doorways, corridors, and cover positions emerge naturally from the data
structure. Attention flows through gaps because gaps have nodes. No scripted "check
doorways" logic anywhere.

> **Revised (October 2026).** True for where an enemy can *be*; not enough for where someone can *see* or
> *shoot*. Windows, fences and low walls are sight lines without navmesh; the barrel can hit cover the eyes
> see over. So rays came back, but only at decision points (where to hold a corner, can the muzzle reach
> the chest — about 0.3 ms per decision), plus a sight map baked offline from the level's collision mesh
> and verified against the engine's own `ray_pick`. Belief itself still lives on the navmesh.

---

## Why Mass Is Objective and Rank Bends Thresholds

An early design option was per-NPC belief mass: each soldier has their own confidence
level, shaped by their rank.

This was rejected because it breaks the "cheap core" invariant:

- Per-NPC mass = N mass values to compute and store per tick per squad
- Shared objective mass = 1 value, computed once, read by everyone

The same effect is achieved more cheaply: mass is a property of *time* (objective,
shared), and rank shifts the *threshold* at which each soldier acts on it.

```
Rookie clinical threshold:  0.08  →  chases belief until it's almost gone
Master clinical threshold:  0.40  →  discards thin belief, moves on
```

> **Note (October 2026).** The principle holds and spread to new systems (grenade skill, wear, weapon
> knowledge). The engine audit added a caveat: X-Ray clamps rank before weapon accuracy and rank immunity,
> so in vanilla every NPC shoots with the same base spread whatever the rank. Rank matters only where a mod
> makes it matter. The next step on this line is a statistical portrait of a fighter instead of one number.

"Rank-based cognition" without per-NPC state. The core stays at constant cost regardless
of squad size.

---

## Why Bearing Points Away from Observer, Not Toward Movement Direction

The first implementation used *inertial bearing*: the predicted direction was the
enemy's last observed movement vector ("they were going that way, keep going that way").

This was a categorical error. It works for an unaware target in transit. It is wrong
for the only moment the system is designed for: *mutual armed contact*.

In mutual contact, a rational actor's intention **inverts**: the enemy is not continuing
their approach — they are fleeing. The inertial bearing pointed the cone toward the
shooter's own feet — into empty ground between the two combatants.

Correct bearing: `LKP − observer_position`, normalized. Points in the direction of
*escape from the observer*. The navmesh then filters this to walkable retreat paths.

---

## Why Belief Doesn't Run Policy (Yet)

VARKA currently controls *eyes* (gaze sweep) and *memory* (belief channels). It does
not yet control *feet* or *decisions*.

This is a deliberate gate: **perception must be validated before policy reads it**.

Connecting a behavior system to belief before the belief model is verified would make
debugging impossible — a wrong movement could come from bad belief *or* bad policy, with
no way to tell which. The layers are built and confirmed sequentially for exactly this reason.

The policy architecture (utility AI at soldier level, market-based task allocation at
squad level) is fully designed and documented in the internal logs. It is not parked
because it is unimportant — it is parked because building layer 2 on unvalidated layer 1
is building on sand.

> **Revised (20 October 2026).** The gate was lifted: the director is the main idea of the mod, and
> perception could not be judged without fights. The protection the gate gave is now given by measurement —
> telemetry of every event and series of matches — and by one structural rule: belief (knowledge) never
> calls hands (decisions); hands read belief.

---

## The Known Open Risks

**Approach path predictability.**
Even a correct belief model doesn't help if the physical path a soldier takes to
reach the belief region is geometrically predictable. The navmesh may route all soldiers
through the same corridor regardless of where they think the enemy is. This is a
*motion* problem, not a belief problem. Mitigation: directional approach cone (soldier
exposes a partial silhouette, sweeping on approach rather than materializing at a fixed
point). Not yet implemented.

**Engine combat timer (60s).**
The X-Ray engine drops the "enemy" flag after 60 seconds of no visual contact
(`xr_combat_ignore`). This returns the NPC to their job regardless of belief state.
VARKA addresses this via `set_enemy()` on non-visual events (audio, corpse channels),
but the timer behavior under repeated `set_enemy` calls is an empirical question
requiring in-engine validation.

**Belief without feet.**
Until a "movement consumer" reads belief and drives NPC navigation, the belief model
is only as powerful as the engine's own threat response. NPCs may correctly *know*
where the enemy probably is and still walk away because their engine-level alert timer
has expired. This is the next architectural boundary to cross.

> **Status (October 2026).** Approach paths: still open; peek and hold-the-edge with a corner ambush
> (`varka_clear`) are the first answer. Engine timer: still unverified. Belief without feet: crossed —
> search, peek, hold, regroup and orders are hands in the main planner.

---

## Decisions added since v0.11

**Own actions only in the main planner.** The engine's C++ combat sub-planner assumes it only ever holds its
own action ids; a custom id there crashed the game when a killer shouted "enemy down". VARKA's actions live in
the main planner and preempt combat through preconditions; the single exception reuses vanilla id 34.

**Yield to vanilla combat when the enemy is in sight.** Vanilla fighting at contact is decent; what it lacks is
everything around contact — losing the enemy, searching, regrouping, surviving a flank. VARKA takes those
moments and hands contact back, adding only gates that make vanilla fire honest (no shot while turned away,
none into cover at the muzzle, friendly-fire check by real geometry).

**Measure outcomes, not spectacle.** A fight that looks smart once proves nothing. Matches are run in series
by a runner, every shot / hit / death is logged, and a change is kept when the numbers move.

**A twin as the game's body, with an empty mind.** The simulation reproduces the game's mechanics from the
engine source (bullet spread, anatomy, speeds, wounds, materials, sight) and is checked against the game's
own numbers. Decisions are pluggable brains, so the same body can run vanilla behaviour, VARKA's, or a learner.

**Fight pure vanilla in the same game.** To compare honestly, a squad can be marked "pure vanilla": every VARKA
hook skips it, and overridden vanilla files route it to an untouched copy of the original function. The world
(fuse times, sight parameters) stays shared — only the mind differs.

**Honest physics over dice.** Where vanilla rolls a die to make NPCs worse (deliberate grenade misses, random
throw power), VARKA replaces it with a skill error that grows with distance and shrinks with rank, and with the
real-world fuse of the grenade.

**Copyleft.** VARKA is a community mod: GPL-3.0-or-later for game scripts, AGPL-3.0-or-later for tools, CC BY-SA 4.0 for documents, so whatever is
built from it stays as open as it is.

