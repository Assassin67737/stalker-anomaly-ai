# Parked scripts

Code that once ran in VARKA and is no longer installed. Kept for history and for parts worth reviving.

| File | What it was | Why parked |
|------|-------------|------------|
| `varka_search.script` | v0.8 gaze sweep across the belief fan | Folded into `varka_search_action` (one machine: gaze + feet + HOLD) |
| `varka_windows.script` | On-demand firing-line primitives (ray_pick over the navmesh) | Replaced by `varka_eyes` (same idea, cheaper API) |
| `varka_baker.script` | Research probe: navmesh bake in game | Superseded by offline bakes in `tools/twin` (level.ai / level.cform parsers) |

Do not copy these into `gamedata/scripts` — nothing calls them.
