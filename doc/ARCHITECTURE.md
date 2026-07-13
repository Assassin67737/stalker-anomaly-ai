# VARKA — Architecture

> How the belief system is built, and why.
> For the design *decisions* behind each choice, see [DESIGN.md](DESIGN.md).
> For term definitions, see [GLOSSARY.md](GLOSSARY.md).

---

## The Problem in One Sentence

Vanilla STALKER NPCs forget the player ~2 seconds after losing line of sight.
There is no persistent memory of *where the enemy probably went*.
Kill → hide → wait → repeat. The exploit runs forever.

VARKA adds an honest belief layer: a lightweight geometric model of what the squad
*thinks it knows* about the enemy, which diffuses, ages, and is fed by sound and corpses —
not only by direct vision.

---

## The Two Axes of Belief

Every belief object carries two orthogonal properties:

```
Geometry  →  WHERE the enemy might be  (cone: position, bearing, angle, reach)
Mass      →  HOW MUCH to trust it      (scalar 1.0 → 0.0, decays over time)
```

**Geometry** answers spatial questions: which navmesh nodes to search, which direction
to face, where to expect contact.

**Mass** answers confidence questions: should this belief drive behavior at all? A Master
stops chasing low-mass belief early. A Rookie keeps searching well past the point of
usefulness. Same belief object, different thresholds — rank-based cognition with zero
per-NPC state in the core.

```lua
-- The full belief structure
belief = {
    pos         = vector,       -- LKP (last known position)
    bearing     = vector,       -- inferred direction of enemy movement (away from observer)
    stamp       = number,       -- time_global() at last update (milliseconds)
    dead_raw    = false,        -- tombstone flag: prevents stale engine memory from reviving belief
}

-- Derived at query time (not stored):
-- mass(b, now)       = max(0, 1 - (now - b.stamp) / LIFETIME_MS)
-- cone_angle(b, now) = BASE_ANGLE + SPREAD_RATE * (now - b.stamp)
```

---

## The Navmesh as Belief Space

VARKA does not use raycasts to check walls. It uses the navmesh.

The navmesh is a 2D walkable surface baked into each map. A human can only stand where
there is a navmesh node. A wall has no nodes — it is simply *missing data*.

The belief cone is sampled by firing K rays via `level.vertex_in_direction()`. When a ray
hits a wall, it doesn't advance — the blocked direction yields no node. The cone is not
"blocked by a wall"; it has a *hole where the wall is*. Attention flows through doorways
because doorways have nodes.

```
Wall = absence of nodes = hole in data
Door = nodes exist      = attention flows through naturally

No hardcoded "wall blocking" logic. Emergence from data structure.
```

This means all occluded search behavior — NPCs paying attention to doorways, corners,
gaps — emerges automatically from the navmesh geometry, not from scripted rules.

---

## The Fan Technique

Since the navmesh has no API to "get all nodes in a cone", VARKA samples it with a fan:
K directional rays spread across the cone angle, each stepped via `vertex_in_direction`.

```lua
local function search_nodes(b, now, threat_pos)
    local nodes = {}
    local cone  = cone_angle(b, now)
    local reach = BASE_REACH + CREEP * (now - b.stamp)
    for i = 1, K do
        local angle = -cone/2 + (i-1) * (cone / (K-1))
        local dir   = rotate_y(b.bearing, angle)
        local vid   = level.vertex_in_direction(base_vid, dir, reach)
        if vid ~= base_vid and vid ~= 4294967295 then  -- valid, not blocked
            local cover = COVER_FLOOR + level.high_cover_in_direction(vid, toward_threat)
            table.insert(nodes, { vid = vid, pos = level.vertex_position(vid), w = cover })
        end
    end
    table.sort(nodes, function(a,b) return a.w > b.w end)  -- cover-heavy nodes first
    return nodes
end
```

Cover weighting (`high_cover_in_direction`) means the sweep naturally prefers cover positions
over open ground — a searching soldier gravitates toward where a rational person would hide.

**snap_to_mesh correction:** if LKP is off the navmesh (enemy on a crate, etc.), the base
vertex for the fan would be invalid (returning `4294967295` for every ray — total blindness).
VARKA walks LKP toward the nearest reachable node before casting, recovering partial visibility.

---

## The Three Channels That Feed Belief

Vanilla: belief is fed only by direct visual contact (`best_enemy` is alive).
VARKA adds two non-visual channels:

| Channel | Trigger | Source of position |
|---------|---------|-------------------|
| **Visual** | `best_enemy` seen | `npc:memory_position(enemy)` |
| **Audio** | `WPN_shoot` / `WPN_hit` heard within 60m, no current enemy | Sound position from `on_hear_callback` |
| **Corpse** | `best_danger() == entity_corpse` of an ally, first time only | `db.storage[corpse].killer_last_known_position` |

All three channels call the same `notice(npc, pos)` API, which plants or refreshes belief
and re-raises the enemy flag via `npc:set_enemy(killer)`.

```lua
-- Public API of varka_lkp
get_belief(npc)            -- returns belief for npc's squad, or nil
notice(npc, pos)           -- plant/refresh belief from external event
geometry(b, now)           -- returns { angle_deg, reach_m }
search_nodes(b, now, threat_pos)  -- returns fan nodes sorted by cover weight
```

---

## Squad-Shared Memory

One belief object per squad, not per NPC. All members read the same object.

Merging rule when a new observation arrives:
- If new stamp > stored stamp → replace (fresher wins)
- If positions are close → average them
- If positions are far → keep both as separate cones (squad attention splits across two regions)

This means an NPC who rejoins a firefight already in progress immediately inherits the
squad's working hypothesis — no cold-start.

---

## Rank as a Threshold, Not a Behavior Branch

Rank affects behavior through *thresholds and multipliers*, never through `if rank == "master" then`.

```
Detection speed      → visual_memory_manager: get_visible_value() × rank_factor
Belief persistence   → clinical_threshold(rank): master=0.40, rookie=0.08
Combat patience      → (planned) combat_ignore duration × rank
```

The same code path runs for every NPC. Rank shifts where along a curve each NPC sits.
No special cases. No hidden branches for "legendary" NPCs.

---

## Current File Map

```
gamedata/scripts/
├── varka_lkp.script      Core belief: storage, update, API, mass, fan, snap_to_mesh
├── varka_search.script   Consumer 1: gaze sweep across fan nodes on contact loss
└── varka_alert.script    Consumer 2: audio + corpse channels → notice() + set_enemy()

gamedata/configs/creatures/
└── m_stalker.ltx         still_visible_time, danger timings (v0.1)

gamedata/scripts/ (modified vanilla)
├── visual_memory_manager.script   detection speed × rank (v0.3)
└── xr_danger.script               danger reactions, corpse channel support (v0.2–v0.5)
```

Everything runs in Lua (LuaJIT). Zero C++. Zero raycasts for belief geometry.
