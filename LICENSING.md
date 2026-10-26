VARKA — community mod. Everything here is free to take, change and share,
and everything built from it stays free the same way (copyleft).

Since 25.10.2026 (v0.26). Releases up to and including v0.25 were published under
MIT / CC BY 4.0 and stay available under those terms. Everything published from
v0.26 on — code and design documents — is under the copyleft terms below only:
no part of it may be taken into a closed or proprietary product.

---

## Game scripts (src/varka_*.script and other original scripts in src/)

Copyright (C) 2026 Ibra

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

Full text: LICENSE (GPL-3.0-or-later).

---

## Tools (tools/: twin, constructor, match runner, viewers, varka_report.py)

Copyright (C) 2026 Ibra

GNU Affero General Public License, version 3 or (at your option) any later
version (AGPL-3.0-or-later). The same as the GPL, plus section 13: whoever runs a
modified version so that people use it over a network (a server, a web service,
an API) must offer those people its complete source under the same license.
Hosting the tools as a closed service is therefore not allowed.

Full text: tools/LICENSE (AGPL-3.0-or-later). Exception: tools/twin/levels/
(data baked from the game, see below).

Since 26.10.2026. Copies of tools/ published between 25.10.2026 and that date stay
available under GPL-3.0-or-later; copies from v0.25 and earlier under MIT.

---

## Design documents (doc/)

Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
You may copy, translate and adapt the documents, credit the source, and you must
release your adaptations under CC BY-SA 4.0 as well. You may not offer them under
any other or additional terms, and may not lock them with DRM (CC BY-SA 4.0 §3(b)).
Commercial use is allowed; closing is not.

Full text: LICENSE-DOCS. https://creativecommons.org/licenses/by-sa/4.0/

---

## Modified vanilla files (src/visual_memory_manager.script, src/xr_danger.script, ...)

src/visual_memory_manager.script, src/xr_danger.script, src/rx_ff.script,
src/axr_fight_from_cover.script, src/xrs_kill_wounded.script and
src/configs/creatures/m_stalker.ltx are derived from S.T.A.L.K.E.R. Anomaly files
and retain the licensing terms of the Anomaly project. VARKA's own modifications
in them are offered under GPL-3.0-or-later as far as those terms allow.

---

## Data baked from the game (tools/twin/levels/)

The level maps, navmesh images, smart-terrain lists and material tables in
tools/twin/levels/ are extracted from the game's level files (level.ai, spawn,
materials). They are data of S.T.A.L.K.E.R. Anomaly and its original authors, not
VARKA's own work, and are not covered by the AGPL or GPL above. They are included
only so the tools work with Anomaly. The scripts that bake them are VARKA's own
(AGPL-3.0-or-later, see Tools).

---

## Code by other authors (src/varka/illish/)

Author: bellyillish — Useful Idiots, https://github.com/bellyillish/useful-idiots
Copied verbatim from v1.4.10 (7bc063668fc004b4b2e6987ea89e15bb76dc6c3b); VARKA
changed only the `require` paths. Released by its author into the public domain
under The Unlicense (src/varka/illish/LICENSE). VARKA does not relicense it: these
files stay public domain, with their author's name kept on them.
