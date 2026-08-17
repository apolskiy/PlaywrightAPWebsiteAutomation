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

## v1.3.0 - 2026-08-16

### Added

- **Every test now carries an assigned, stable identifier.** Forty-two tests are
  marked `PAWA_10001` through `PAWA_10042` via `@pytest.mark.test_id(...)`;
  the next free number is `PAWA_10043`, and numbers are never reused.

  The identifier exists because a test's name is not a stable identity. Any
  store keyed on the name forks a test's history the moment it is renamed -
  silently, because both halves still look like valid tests, and the only
  symptom is one long record quietly becoming two short ones. Names should stay
  free to improve; this is what makes that free.

  `conftest.py` republishes the marker at collection time in `_publish_test_ids`, as
  both an Allure label and a JUnit `<property>`, so it is authored once and reaches two
  reporters that do not talk to each other. Collection time rather than a fixture,
  deliberately: the label is attached before any reporter begins building a result, so it
  cannot be lost to fixture ordering.

  Verified end to end - a single-test run produced an Allure result carrying
  `PAWA_10020`, and collection still reports the full 74 items.

- **`test_id` registered as a marker.** Required rather than cosmetic: this suite runs under `--strict-markers`, so an
  unregistered marker is an error, not a warning.

### Notes

- No test was renamed and no behaviour changed. The diff is decorator
  insertions plus the collection hook.
- The identifier is additive for history: the collector keys on
  `COALESCE(test_id, test_uid)`, so results recorded before these IDs existed -
  including artifacts now expired - still stitch to results recorded after.

---

## v1.2.3 - 2026-08-12

A documentation clarification. **Patch**: no source, configuration or test
changed.

### Changed

- **The published-artefact check now states what it does not cover.** It reads
  the image's dependency closure from the registry and never asks the container
  to serve a request, so a stale build would satisfy it. That behavioural half
  now runs in PublicAP's own CI, where a container runtime is already available,
  and the README cross-references it. The split is what keeps each side cheap:
  this repository verifies the claim its own page makes about the artefact's
  contents, and the artefact's repository verifies that the artefact works.
  Stating the boundary matters more than it sounds - a check whose limits are
  unwritten gets trusted for things it never did.

---

## v1.2.2 - 2026-08-12

A documentation correction backed by a measurement. **Patch**: no framework
source, configuration or test changed.

### Fixed

- **The suite's browser coverage was described inconsistently in four places.**
  `requirements.txt`, this repository's README and the site's README all said
  the suite was verified on Chromium and Firefox, with WebKit untested; the Web
  Automation tab said it "runs on Firefox and WebKit on request", which reads as
  WebKit being covered. Three sources said one thing and the fourth implied
  another.

  The disagreement was resolved by running the suite rather than by choosing a
  wording. WebKit turned out not to be installed for the pinned Playwright
  release at all - `webkit-2311` was required, `webkit-2227` was present, and
  every test errored at browser launch. Installed and run, **all 72
  deployment-path tests passed on all three engines**, measured 2026-08-12
  against the live site on one Windows machine:

  | Engine | Result | Wall clock |
  | --- | --- | --- |
  | Chromium | 72 passed | 34.6s |
  | WebKit | 72 passed | 52.1s |
  | Firefox | 72 passed | 102.7s |

  So the claim that needed correcting was the conservative one, not the
  optimistic one. All four sources now state the measured result, dated, with
  the caveat that these are single runs over a real network rather than a
  controlled benchmark.

### Changed

- **The "Why Chromium only" rationale now rests on the measurement.** It
  previously asserted that WebKit on Linux runners is the noisiest of the three,
  which nothing in this repository had measured. Replaced with what the figures
  actually support: three engines agreeing exactly is the expected result for a
  page with no engine-specific surface, and re-proving it per push would cost
  about 3.4x the wall clock. The argument that carries more weight is unchanged
  and is now stated first - this pipeline gates a deployment signal, and extra
  engines re-admit unrelated red into it, which is the same reason `external`
  tests are already deselected.
- **Playwright's WebKit is now distinguished from Safari** wherever the pass is
  claimed. It shares the renderer, not Safari's platform integration, so the
  result is evidence the page is engine-neutral rather than evidence that Safari
  works.

---

## v1.2.1 - 2026-08-12

### Fixed

- **A README feature bullet quoted "12 of 73 tests", a total the suite left
  behind in the same release that introduced the sentence.** v1.2.0 took the
  suite to 74, so the paragraph describing what changed carried the pre-change
  figure with no tense marking it as history. The site had the same sentence in
  an outcome row, where it sat two clicks from a published, self-verifying 74 -
  reported as a defect, and correctly.

  Both now say only the per-route load checks recorded anything and nothing that
  clicks did. That was always the claim; the denominator was decoration, and
  decoration that goes stale on the next test added. The figure in `CHANGELOG.md`
  is untouched - a changelog entry is dated and describes the state at its
  release, which is exactly where a superseded number belongs.

---

## v1.2.0 - 2026-08-12

### Added

- **`utils/page_diagnostics.py`, and with it the browser's error log on every
  page in the suite.** `PageDiagnostics` records console errors, requests that
  failed at the network level, responses of 400 and above, and unhandled
  JavaScript exceptions. `BasePage` constructs one, so every Page Object carries
  it and the fixtures arm it before the first navigation - Playwright delivers
  no event that predates its listener, so recording cannot be retrofitted after
  a failure.

  The recording itself is not new; its reach is. It lived on `RoutePage`, which
  meant it covered 12 of 73 tests and only the load path: navigate, read the
  log, done. The ~61 landing-page tests recorded nothing, and those are the ones
  that click - the tab router and the base64 link decoder are the only scripts
  this site runs, and neither executes until a visitor does something. An
  exception thrown by either was invisible to the whole suite. What it produced
  instead was a locator timeout, which reports that an element never appeared
  and says nothing whatsoever about why.

- **`tests/test_runtime_health.py`**, one test that walks all seven tabs in
  order and then requires the log to be clean. One test rather than one per tab
  on purpose: the router is a state machine over a shared page, so the failures
  worth catching are the ones that need a sequence - a listener bound twice, a
  panel left visible, a decoder run again over already-decoded markup - and a
  per-tab test reloading between clicks would reset the state that produces
  them.

- **The error log is now an input to Claude failure triage.** `FailureContext`
  carries a `browser_diagnostics` field and the prompt renders it as its own
  section, ahead of the DOM.

  The two inputs answer different halves of the question. The DOM shows what the
  page ended up as; the log shows what went wrong on the way there, and it
  frequently names the cause outright - a script that threw before it could bind
  the tab router explains a missing panel far more directly than the absence of
  that panel does. Sending only the DOM was asking for a cause while withholding
  the evidence for it.

  The system prompt gained instructions for reading it, because the log is only
  useful if its structure is understood: an unhandled exception is the strongest
  signal available given that this site's only scripts are the router and the
  decoder; a failure supported solely by third-party events is a flake, since
  the suite deliberately does not fail on those; and an empty log is evidence
  rather than an absence of it, ruling out script exceptions and missing
  resources.

  The field is required rather than optional. A caller with nothing to report
  passes the report of a recorder that saw nothing - which *states* that no
  errors occurred, a materially different claim from omitting the section, and
  one the prompt now reasons from explicitly.

- **`MAX_DIAGNOSTICS_CHARS`** (8,000) in `config/settings.py`, bounding that
  input the way `MAX_DOM_SNAPSHOT_CHARS` bounds the DOM. The smaller budget
  reflects that the log is already a summary - but it is not bounded by the
  page, and a request loop or a script erroring on every frame can produce
  thousands of near-identical lines. Truncation of either input is now announced
  in the prompt text by a shared helper: a model reasoning over a fragment it
  believes is complete will report that something is absent when it was merely
  cut off, which is a confident wrong answer rather than a missing one.

- **`BasePage.settle_sub_resources()`**, a short, non-fatal wait for the `load`
  event before the log is read. Every navigation here waits for
  `domcontentloaded`, which is the right readiness signal for interacting with
  the page and the wrong one for reading its error log: at that moment the
  sub-resources are still in flight, so a check reading the log immediately is
  racing them. A timeout is not an error - the page embeds badges served by
  GitHub, and failing on a slow third party is exactly what this release is
  removing - so a caller that did not settle says so in its failure message
  rather than failing on the wait.

### Changed

- **The error log is attached to every failure, by the failure hook rather than
  by the test.** Previously it was read only by the one test asserting on it and
  discarded at teardown otherwise: a mobile-overflow failure would tear down a
  page whose recorded console log might have explained it outright. It is now
  attached to Allure alongside the screenshot, DOM and trace, and published as a
  pytest report section so it also appears beneath the traceback in the terminal,
  in the CI log, and in `reports/pytest-report.html`.

  It is attached first and outside the screenshot capture block, because the
  events are already in memory: it is the one piece of evidence that survives a
  page which has closed under the test.

- **Network assertions in `test_route_loads_without_console_or_network_errors`
  are now scoped to the site's own origin, which removes an unintended
  third-party dependency from the deployment path.** Every project panel embeds
  a CI badge image served by `github.com`. The test asserted that no
  sub-resource returned an error status, ran against `/`, and was not marked
  `external` - so a 5xx from GitHub could fail the deploy signal. It did not
  fail in practice mainly because the assertions ran at `domcontentloaded` while
  the badge responses were still in flight; the check was racing the images,
  which makes it a nondeterministic dependency rather than an absent one.

  Verified rather than argued: with the badge host forced to answer 503, the
  recorder logs 10 events, all of them third-party, and every first-party list
  stays empty. Under the previous code those 10 would have failed the run.

  Unhandled JavaScript exceptions are deliberately not scoped this way. An
  exception is raised by a script this site chose to run, whoever served it.

- **`RoutePage` no longer records anything itself.** Its four diagnostic
  properties and four event handlers moved to the collaborator, leaving a Page
  Object that navigates a route and reads what it rendered. Call sites read
  `route_page.diagnostics.first_party_console_errors`, the same shape as
  `landing_page.links.outbound_targets()`.

- Suite size is now **72 tests on the deployment path, plus the 2 `external`
  ones - 74 in total**. Written as a sum rather than as a pair: the two figures
  had been quoted as a total followed by a subset, which shortens to "74/72" and
  reads as a fraction whose denominator is smaller than its numerator. The site
  publishing them was reworded the same way in its own v1.2.0.

### Fixed

- **Stale figures in the README's *Dynamic Site Discovery* section.** It still
  described five health checks per route and ten dynamic tests; the meta
  description check added in v1.1.0 made those six and twelve. The section stamp
  had not been moved with that release, which is the failure mode the stamps
  exist to make visible - and did, on the next read.

### Notes

- No test was added for the recorder itself. It is exercised by the two tests
  that assert on it and by the failure hook on every red build, and a unit test
  over a stubbed `Page` would assert that Playwright delivers its own events.

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
