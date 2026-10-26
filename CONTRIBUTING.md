# Contributing to VARKA

VARKA is a community mod. Patches, test reports, match logs and design notes are welcome.
This page covers the rules a contribution has to follow before it can be merged.

## Your contribution stays yours, and stays open

There is no CLA and no copyright assignment. You keep the copyright on what you write, and you
license it to everyone under the same terms as the part of the project it goes into:

| Where it goes | License |
|---|---|
| `src/` (game scripts, configs) | GPL-3.0-or-later |
| `tools/` (twin, sim, match runner, viewers) | AGPL-3.0-or-later |
| `doc/` (design documents) | CC BY-SA 4.0 |

Nobody, the maintainer included, can relicense your work to closed or permissive terms without
your consent. The more people contribute this way, the harder VARKA becomes to close. The project
works this way on purpose. Full terms: [LICENSING.md](LICENSING.md).

## Sign off every commit (DCO)

Each commit must end with a `Signed-off-by` line, which certifies the
[Developer Certificate of Origin](#developer-certificate-of-origin-11) below:

```
Signed-off-by: Your Name <you@example.org>
```

`git commit -s` adds it for you. Use the name and address you are known by in the community; a
consistent handle is fine, an anonymous one-off is not. The sign-off transfers no rights. It says
the code is yours to give, or comes from a source whose license lets you give it.

Forgot it? `git commit --amend -s` for the last commit, `git rebase --signoff main` for a branch.

## What cannot go in

- **X-Ray engine source code**, copied or translated, including from leaked or community engine
  forks. Reading the engine to learn a file format is fine (`tools/twin/level_ai.py` does that); copying
  its code is not.
- **Game files and assets** from Anomaly or S.T.A.L.K.E.R.: models, textures, sounds, whole configs or
  scripts. The few vanilla files VARKA replaces are listed in `LICENSING.md`. A new one needs to be
  discussed first, and must be added to that list.
- **Data extracted from the game** outside `tools/twin/levels/`. Commit the script that bakes it.
  The baked output belongs to the game's authors and must be labeled as such.
- **Code from another project without its license and author.** Compatible licenses (public
  domain / Unlicense, MIT, BSD, Apache-2.0, LGPL, GPL-3.0) are welcome. Keep the code verbatim, keep
  its license file next to it, and add the author to "Code by other authors" in the README, as done
  for `src/varka/illish/`.
- **Code you cannot vouch for**: from a closed project, from an employer that owns your work, or
  from a source you do not know.

AI-assisted code is accepted on the same terms. You sign off for it, so read it, test it, and
make sure it does not reproduce someone else's code. Say in the pull request that it was written
with AI help.

## How to send a change

1. Fork the repository and work on a branch in your fork.
2. Test in game: follow the Installation section of the [README](README.md), and check
   `appdata/logs/xray_<user>.log` for Lua errors first.
3. Write commit messages the way the history does: `area: what changed` (for example
   `grenades: fuse follows real time`). Say what you verified in game and what is untested.
4. Open a pull request against `main`. The maintainer reviews and merges.

## Developer Certificate of Origin 1.1

```
Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

Source: https://developercertificate.org/ (The Linux Foundation and its contributors).
