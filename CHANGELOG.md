# Changelog

All notable changes to this framework are recorded here. `README.md` always
describes the **current** release and nothing else; this file is where
release-to-release history lives, so the README never accumulates a sediment of
"as of version X" qualifiers.

Each README section carries the release and date its content last changed
(`<sub>v1.0.0 &middot; 2026-08-10</sub>`). Together the two answer different
questions: the stamp tells a reader arriving at a later version *which sections
moved*, and an entry here tells them *what changed and why*. A changelog entry
alone does not tell you where to look.

Versions follow [Semantic Versioning](https://semver.org/) as applied to a test
framework:

- **Major** - a change that breaks an existing invocation or configuration.
- **Minor** - new coverage, new capability, or a new quality gate.
- **Patch** - fixes and documentation corrections that change no behaviour.

Dates are **UTC**, matching git commit dates and CI runners, so a stamp written
in the evening in one timezone still agrees with the commit that carries it.

---

## v1.0.0 - 2026-08-10

First release under version tracking. The framework predates this file;
commit-level history before this point is in git. This entry records the state
as shipped, and the changes that landed with it.

### Added

- **Coverage for the VM Cluster Deployment tab.** `NavigationTab` gained the
  tab, which is the only declaration required: `test_navigation.py`,
  `test_project_panels.py` and `test_engineering_outcomes.py` all parameterize
  over that enum, so the tab contributed five cases with no edit to any test
  module.
- **`test_project_panel_rows_agree_on_one_repository`.** A project panel's
  repository row, CI badge source and README target are each reduced to the
  `owner/name` they belong to and required to agree. Every one of those rows was
  already asserted individually, and every one of those assertions passes on a
  panel that is quietly describing two different projects: the badge check can
  only require a source under this author's account, which is true of every
  repository he owns. A panel begun by copying a sibling therefore keeps the
  sibling's badge and stays green while reporting a build result that belongs
  somewhere else - on the one row of the page whose entire purpose is to say
  whether *this* project works, and with nothing about it visible from the
  rendered page. One case per project.
- **`CHANGELOG.md` and per-section documentation stamps** in `README.md`.

### Changed

- Suite size is now **71 tests**, of which **69** run on the deployment path.
  Both figures are published on the target site and read back by
  `test_published_suite_size.py`, so this entry and the site agree by
  construction rather than by remembering.
- `pages/landing_page.py` gained `repository_link()` and the module-level
  `github_repository()` helper, which reduces any GitHub URL to the repository
  it belongs to.
- **The outbound-link auditor moved out of the Page Object** into
  `utils/link_auditor.py`. Adding the repository-agreement accessor pushed
  `LandingPage` past the `max-public-methods` ceiling, and raising the ceiling
  would have been the second raise. The ceiling was right: the class had grown a
  part that was not page interaction at all - collecting anchors, separating
  outbound targets from internal ones, and resolving each against its host with
  per-host pacing, which issues real HTTP requests to third parties and keeps
  timing state the page has no business owning. `LandingPage` went from 51
  public methods to **45**, and the ceiling stayed at 50. The collaborator is
  reached through a `links` attribute, so the call sites read
  `landing_page.links.outbound_targets()`.

### Notes

- CI remains **Chromium-only** by decision rather than by omission; the
  reasoning and the conditions that would reverse it are in the README under
  *Quick Start*.
- The two `external` tests - outbound link rot and the published container
  image - stay off the deployment path and run weekly. A deploy signal has no
  business depending on whether GitHub or Docker Hub is reachable from a runner.
