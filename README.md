# VARKA — Honest Combat AI for S.T.A.L.K.E.R. Anomaly

> *"Complex not smart."*

> Early work in progress for S.T.A.L.K.E.R. Anomaly 1.5.3 with Modded Exes.

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
