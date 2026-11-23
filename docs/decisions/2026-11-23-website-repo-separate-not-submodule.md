# Website repo: separate repo, not a submodule

**Date:** 2026-11-23
**Status:** Proposed. Accepted when Alex approves the template PR.
**Ticket:** ATB-200 (spike, parent ATB-129)
**Supersedes:** the "Website repo added as git submodule at `website/`" line in
[2026-03-22-prim-agent-repo-structure-adopted.md](2026-03-22-prim-agent-repo-structure-adopted.md)
**Brief:** `AllThatBrand/project_terabeauty` → `docs/designs/deploy-pipeline-spike.md`,
§5 "Website repo: separate, not a submodule" and "Alternatives Weighed" (ATB-195)

## Decision

The default for a new project is **(b): a separate website repo**. The project repo
records the repo's URL and the expected checkout path. It never embeds the repo.
The template no longer adds a `website/` submodule.

**(c) site code inside the project repo** is allowed as an exception, for a site
without a CI deploy (manual zip or SFTP upload). That code lives under `site/`, and
nothing deploys from the repo root.

**(a) a submodule** is no longer offered as an option for new projects.

## Options compared

| | (a) submodule at `website/` | (b) separate repo, referenced | (c) code in project repo |
|---|---|---|---|
| **Role in the deploy** | None. The ATB-142 pipeline runs from the website repo. The pointer is never read. | The deploy runs from this repo (ATB-142). | The project repo becomes a deploy source. Every docs or digest merge needs a path filter, or it triggers a deploy. |
| **Pointer drift / bump commits** | Needs a "bump" commit after every site change, or it drifts. Measured: `project_hhow` → `hhow-booking` was added on 2026-04-27, never bumped, now 13 commits behind `main`. | None. Nothing to bump. | None. |
| **Agent and IDE access** | In-tree, but at a stale commit unless someone runs `git submodule update --remote`. Easy to edit a detached HEAD by mistake. | A sibling checkout added to the session (Claude Code `--add-dir` / "Add folder", a second IDE root). Always on its own branch. | In-tree. Simplest. |
| **Publishing risk of the deploy root (ATB-129 §9)** | Low. Docs and site stay in separate repos. | Lowest. The website repo carries only `wp-content` code. | Highest. `AGENTS.md` / `CLAUDE.md` were publicly served once when a repo root was the deploy root. Safe only if the deploy targets `site/`. |
| **Windows checkouts** | Extra steps: `--recurse-submodules` and credentials for a second private repo. | Two plain clones. The release-swap symlinks exist only on the server, so Windows never sees them (brief §5). | One clone. |
| **Onboarding a new project** | `git submodule add` plus a pointer policy that nobody follows. | Create the website repo from `atb-starter-theme` (pipeline included) and write its URL in `.agent/project.md`. | Create `site/`. No pipeline. |

The ATB repos today: the website lives in its own repo for `atb-starter-theme`,
`allthatbrand.ch`, `hhow-booking` and `swisshairdoctor-wp` (b).
`project_swimatic/site/` and `project_sorry-not-sorry/site/` hold mu-plugins, theme
and zip builds deployed by hand (c). Only `project_hhow` uses a submodule (a).

## Answers to the spike questions

1. **Default:** (b), with (c) allowed for sites without a pipeline. Reasons:
   - the submodule has no role in the deploy;
   - the one real submodule drifted within months;
   - (b) keeps docs out of the deploy root by construction.
2. **Reaching the site code without a submodule:**
   - Clone the website repo next to the project repo: `<workspace>/project_<client>` and
     `<workspace>/<website-repo>`. `.agent/project.md` records the URL (`Repo (website)`)
     and the checkout path (`Website checkout`).
   - Agents add the sibling folder to the session. A `git worktree` of the website repo
     works the same way for parallel branches.
   - Changes to site code go through the website repo's own PRs and pipeline, never
     through the project repo.
3. **If a submodule is kept:** only on an existing project. It is a **read-only pointer**:
   - It is never bumped per deploy, and no workflow reads it.
   - The PM bumps it only at a release milestone, with a commit `chore: bump <repo> to <tag>`.
   - The deploy state lives in the website repo (its tags and the pipeline's state),
     not in the pointer.

## Migration note for existing projects

- **`project_hhow` (`hhow-booking`): remove the submodule.** It is 13 commits behind,
  no workflow reads it, and `hhow-booking` deploys from its own repo. Steps:
  1. `git submodule deinit -f hhow-booking`
  2. `git rm hhow-booking`
  3. `rm -rf .git/modules/hhow-booking`
  4. Add the repo URL and the sibling checkout path to `.agent/project.md`.
  5. Replace the README line "`website/` Git submodule → HHoW website repo" with that reference.

  This changes nothing on the server. Do it as a separate PR with the project owner's OK.
- **Projects with `site/` (swimatic, sorry-not-sorry):** keep it (allowed exception).
  If one of them moves to a CI deploy, move the site code to its own repo first,
  starting from `atb-starter-theme`.
- **All other projects:** nothing to change. None of them has a `website/` submodule.

## Out of scope

- Changing the deploy workflow (ATB-142).
- Migrating client repos beyond this note.
- Submodule installs of skills (ATB-145), which is a different use case and stays as it is.
