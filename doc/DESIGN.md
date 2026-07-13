# VARKA — Design Decisions

> The *why* behind every architectural choice.
> For *what* was built, see [ARCHITECTURE.md](ARCHITECTURE.md).

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
