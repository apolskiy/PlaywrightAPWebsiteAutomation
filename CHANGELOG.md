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

## v1.1.1 - 2026-08-10

### Changed

- **`test_contact_link_is_decoded_without_exposing_the_address` documents the
  boundary it actually enforces.** The check asserts the address is absent from
  the rendered text while `expect_email_link_decoded` asserts it is *present* in
  the `href` - deliberately, since a contact link that does not carry the
  address is not a contact link. Read quickly, those look contradictory, and the
  test name suggests a stronger guarantee than either provides.

  The docstring now says so: the address is visible in the status bar on hover
  and in devtools, that is inherent to a working anchor rather than a gap in the
  check, and the obfuscation defeats only scrapers that read HTML without
  executing it. No assertion changed - the suite was already testing exactly the
  right thing, and only the reason was missing.

### Notes

- No test was added for the status-bar exposure, because there is nothing to
  assert: every functioning `mailto:` anchor reveals its address that way. The
  corresponding limitation is now stated on the site rather than checked here.

---

## v1.1.0 - 2026-08-10

### Added

- **`test_route_publishes_a_meta_description`**, a per-route check that the page
  declares a `<meta name="description">` and that its content falls between 50
  and 160 characters. Below the floor is a placeholder; above the ceiling is
  text a search result truncates, so it was written for nobody. The two failure
  modes are kept distinct - a missing tag and an empty one are different
  mistakes and get different messages.

  It earned its place immediately, failing on the case-study page at 199
  characters on the first run after it was written. Like the rest of
  `test_dynamic_routes.py` it parameterizes over discovered routes, so a page
  published later without a description fails on the run that first finds it.

- `RoutePage.meta_description()`, which returns `None` for a missing tag rather
  than collapsing that into an empty string, so the caller can tell the two
  apart.

### Changed

- Suite size is now **73 tests**, **71** on the deployment path (6 dynamic
  checks × 2 discovered routes).

- **The document-title check asserts the owner's name instead of a library.**
  It required the title to contain "Playwright", which pinned the site's single
  most visible piece of text - browser tab, bookmark, search result - to one
  entry in a technology list that will keep changing. When the title was
  rewritten to name the person rather than the file types, this check failed,
  which is the check doing its job; but what it was protecting was the wrong
  invariant. It now asserts `PROFILE_NAME`, the same constant the portrait and
  heading assertions already use, so the title, the portrait and the heading
  agree on one source for who the site belongs to.

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
