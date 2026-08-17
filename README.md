# Playwright AP Website Automation Framework
#Aleksandr Polskiy
A production-grade E2E web automation and dynamic route-discovery framework built with Python, Playwright, Pytest, and Claude AI diagnostics.

Target Application: [https://apolskiy.github.io/](https://apolskiy.github.io/)

> **Documentation status:** describes **v1.3.0**, reviewed 2026-08-16.
> Each section below carries the release and date its content last changed, so a
> reader arriving at a later version can see at a glance which parts moved. This
> file always describes the *current* state; release-to-release history lives in
> [CHANGELOG.md](CHANGELOG.md).

---

## Key Features

<sub>v1.2.1 &middot; 2026-08-12</sub>

- **Page Object Model (POM):** Clean separation of UI locators, interaction workflows, and assertion logic. Test modules contain zero raw selectors and never touch a Playwright `Page` directly.
- **Dynamic Site Discovery:** An async Playwright crawler maps the site's route graph at collection time and writes `reports/sitemap.json`. Every discovered route is then parameterized into its own health-check tests, so publishing a new page grows the suite with no test edit.
- **Cross-Viewport Coverage:** Every layout rule is asserted on both sides of the site's `max-width: 600px` breakpoint: desktop (1920x1080) and mobile (390x844).
- **Evidence-Integrity Checks:** The site's Engineering Outcomes tab claims each result is verifiable in source. The suite holds it to that: no outcome row may cite zero projects, and following a citation must open the project tab it names, so a stale `data-target` cannot quietly send a reader to the wrong repository.
- **Panels Checked Against Themselves, Not Just Against a Pattern:** Every project panel must carry a documentation link and a build badge, and each is asserted individually - which passes on a panel that is quietly describing two different projects. The badge check can only require a source under the author's account, and that is true of every repository he owns, so a panel begun by copying a sibling keeps the sibling's badge and stays green while reporting a build result that belongs to somewhere else, on the one row whose whole purpose is to say whether *this* project works. Nothing about it is visible from the rendered page. It is caught by reducing the repository row, the badge source and the README target to the `owner/name` each belongs to and requiring the three to agree.
- **Outbound Link-Rot Detection, Off the Deploy Path:** Every distinct off-site target the page advertises is resolved with `HEAD`, falling back to `GET` for anything that is not a clean success - `HEAD` support is not universal (LinkedIn answers `405` to it), so no build is failed on a `HEAD`-only answer. Only `404`/`410` count as rot: `401`, `403`, `429` and a failed connection mean "not reachable by an anonymous, unthrottled caller". Requests are paced **per host**, because the limit being respected is per host and a global delay would make every target wait on every other while protecting nothing - measured over this site's links, per-host scoping cut the batch from 12.8s to 9.5s. The check is marked `external` and runs weekly rather than per push, so a deploy signal never depends on a third party.
- **Published Figures Verify Themselves:** The site quotes this suite's size in prose, in two places. A hand-maintained number is a number that eventually stops being true - a test is added, the pipeline still passes, and the page keeps advertising last month's figure. The figures stay written in the markup, because a reader should see a number rather than a placeholder, but they are read back and compared against the running suite, so drift fails the build instead of decaying quietly. Counts are taken during collection with a `tryfirst` hook, ahead of the `-m` and `-k` filtering pytest applies in that same hook, so running a subset never makes the published figure look wrong. Two invocations measure something the figure was never describing - naming specific files, and selecting several browser engines - and both skip rather than report drift that is not there.
- **Published Artefact Verification, Off the Deploy Path:** The HTTP Emulators tab claims the `apolskiy/flask_app` image carries Flask and its six transitive dependencies and nothing else. That claim is checked against the image itself: an anonymous pull token, the platform manifest, then the layer blobs, reading the installed `*.dist-info` metadata to assert the closure is exactly what the page advertises. Base packaging tooling is subtracted rather than pretended away. No container runtime is involved - a test needing Docker could not share a runner with the browser suite - and no HTTP client was added, since the standard library already resolves a registry. Marked `external` for the same reason link-rot is: a dependency regression in a published image is a monthly risk, not a per-push one.

  What this check deliberately does **not** cover is behaviour: it reads what the image contains, never asks it to serve a request. That half belongs where a container runtime is already available, and lives in [PublicAP's own CI](https://github.com/apolskiy/PublicAP/blob/master/.github/workflows/image-tests.yml), which runs the emulator's behavioural suite against both a freshly built image and the published one. The two are complementary by design and the split is the reason each can stay cheap: this repository verifies the claim its own page makes about the artifact's contents, and the artifact's repository verifies that the artifact works.
- **Link Auditing Covers Hidden Panels:** Anchors are collected with a CSS locator rather than the `link` role. In a tabbed single-page application every inactive panel is `display: none`, which removes its contents from the accessibility tree - a role-based locator returned only the header and footer, so the link checks were inspecting 2 of 16 published targets while passing. This lives in `utils/link_auditor.py` rather than on the Page Object: it issues real HTTP requests to third parties and keeps per-host timing state, which is a different responsibility from driving the document in front of the browser.
- **The Browser's Own Error Log, on Every Page:** Each Page Object owns a `PageDiagnostics` recorder, armed by the fixture before the first navigation, that collects console errors, requests that failed at the network level, responses of 400 and above, and unhandled JavaScript exceptions. Recording used to live on the route Page Object alone, which meant only the per-route load checks recorded anything: the landing-page tests - the ones that actually click things - recorded nothing, so an exception thrown by the tab router or the link decoder was invisible to the entire suite. What a reader saw instead was a locator that timed out and an error explaining nothing. Every page now records whether or not the running test asserts on it, and the log is attached to every failure.
- **Origin-Scoped Assertions:** The recorder separates what this site is answerable for from what it merely embeds, and only the first can fail a build. Each project panel carries a CI badge image served by GitHub; asserting on an unscoped error log therefore put GitHub's availability in the critical path of every test that loads the page - a third-party dependency arriving through a sub-resource rather than through anything a test does deliberately, and one that only bites intermittently because it races the page load. Third-party problems are still recorded, still counted, and still reported; they are simply not the verdict. Unhandled JavaScript exceptions are the deliberate exception to the rule: an exception is raised by a script this site chose to run, whoever served it.
- **Event-Driven CI/CD Execution:** Runs on GitHub Actions on a push that touches framework sources, on manual `workflow_dispatch`, and on a `website_updated` `repository_dispatch`. Runs are deduplicated by a concurrency group scoped to workflow, event, and ref, so an outdated in-flight run is cancelled rather than racing the latest one.
- **Deployment-Aware Gating:** Before any browser launches, CI waits for the target's Pages deployment to settle: first until the site repository reports no queued or in-progress Actions run, then until the served `ETag` repeats across consecutive polls. An HTTP 200 is not proof of freshness - the previous build answers 200 just as happily - and testing a half-propagated CDN is how a passing locator times out mid-run.
- **Dual Reporting Engines:** Rich interactive **Allure HTML** reports plus standalone **Pytest HTML** execution summaries.
- **AI-Powered Test Diagnostics:** On any failure the suite attaches the browser's error log, a screenshot and a DOM snapshot, then asks Claude to classify the failure and propose a fix - attached to the Allure report as a structured triage note. The model receives the error log alongside the DOM, and the two answer different halves of the question: the DOM shows what the page ended up as, the log shows what went wrong on the way there. A script that threw before it could bind the tab router explains a missing panel far more directly than the absence of that panel does, so sending only the DOM was asking for a cause while withholding the evidence for it. The prompt also tells the model how to read the split: a failure whose only support is third-party is a flake, and an empty log is evidence rather than an absence of it, since it rules out script exceptions and missing resources.
- **Clean Code & Static Analysis:** PEP 8 compliance, Google-style docstrings, and strict type annotations, gated at **Pylint 10.00/10** in CI.

---

## Project Architecture

<sub>v1.2.0 &middot; 2026-08-12</sub>

```text
PlaywrightAPWebsiteAutomation/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Pages-deployment gate, Pylint gate, E2E job, Allure report
│       └── external-links.yml     # Weekly outbound link-rot check (`-m external`)
├── config/
│   ├── __init__.py
│   └── settings.py                # Environment loader, viewport and timeout constants
├── pages/
│   ├── __init__.py
│   ├── base_page.py               # Navigation, viewport, DOM capture, layout measurement
│   ├── landing_page.py            # POM + NavigationTab enum for the portfolio page
│   └── route_page.py              # Generic POM for any crawler-discovered route
├── utils/
│   ├── __init__.py
│   ├── claude_inspector.py        # Claude API failure triage helper
│   ├── link_auditor.py            # Outbound link collection, classification, and resolution
│   ├── page_diagnostics.py        # Console/network/JS error recording, split by origin
│   ├── registry_client.py         # Stdlib Docker registry reader for published-image audits
│   ├── site_crawler.py            # Async sitemap crawler and route discovery engine
│   └── visual_comparator.py       # Pillow threshold image-diff helper (available; no test uses it yet)
├── tests/
│   ├── __init__.py
│   ├── test_navigation.py         # Header integrity and SPA routing
│   ├── test_responsive.py         # Desktop/mobile layout validation
│   ├── test_link_obfuscation.py   # Base64 anti-scraping link and e-mail decoding
│   ├── test_link_styling.py       # Shared interactive link hover styling
│   ├── test_engineering_outcomes.py  # Outcomes table and its cross-tab citations
│   ├── test_project_panels.py     # Per-project panel completeness and repository agreement
│   ├── test_published_image_claims.py  # Published container matches the claim on the page
│   ├── test_published_suite_size.py    # Suite-size figures on the site match the real suite
│   ├── test_runtime_health.py     # Browser error log after the page has been used, not just loaded
│   └── test_dynamic_routes.py     # Health checks generated per discovered route
├── conftest.py                    # Viewport fixtures, suite-size registry, failure diagnostics
├── .env.example                   # Template for local configuration
├── .gitignore
├── .pylintrc                      # Static analysis configuration
├── pytest.ini                     # Pytest, Allure, & browser runtime flags
├── CHANGELOG.md                   # Release-to-release history; this file holds only the present
├── LICENSE
├── README.md
└── requirements.txt
```

`NavigationTab` in `pages/landing_page.py` is the single place a newly published tab is declared, and three suites parameterize over it rather than over a list of their own: `test_navigation.py` takes one case per tab, `test_project_panels.py` four per *project* tab, and `test_engineering_outcomes.py` one per project tab. Adding the VM Cluster Deployment tab therefore contributed **five** cases with no edit to any test module. (`test_responsive.py` iterates the same enum *inside* two tests, so its coverage grows with a new tab while its case count does not.)

---

## Quick Start

<sub>v1.2.2 &middot; 2026-08-12</sub>

Requires **Python 3.10+** - the highest floor declared by any pinned dependency. Developed, verified, and CI-pinned on **3.14**.

```bash
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env      # optional; sensible defaults apply without it
python -m pytest
```

Run against another engine, or all three:

```bash
python -m pytest --browser=firefox
python -m pytest --browser=chromium --browser=firefox --browser=webkit
python -m pytest --headed --slowmo 250          # watch a run locally
```

**All three engines pass.** Measured 2026-08-12 against the live site, on one Windows machine, `-m "not external"`:

| Engine | Result | Wall clock |
| --- | --- | --- |
| Chromium | 72 passed | 34.6s |
| WebKit | 72 passed | 52.1s |
| Firefox | 72 passed | 102.7s |

These are single runs over a real network, not a controlled benchmark: read them as an order of magnitude, not a measurement of the engines. CI installs and runs Chromium only, so Firefox and WebKit are a *verified state* rather than a continuously enforced one, and a regression specific to either would not be caught by the pipeline.

Playwright's WebKit is a build of the engine, not Safari. It shares the renderer but not Safari's platform integration, so the row above is evidence this page is engine-neutral - not evidence that Safari works.

**Why Chromium only.** The three-engine CI matrix was considered and deliberately not built. This target's behaviour rests on ordinary DOM, CSS and `atob` rather than engine-specific APIs, so the residual risk is concentrated in layout - already asserted on both sides of the 600px breakpoint at every viewport. The table above is the argument rather than an objection to it: three engines agreeing exactly is what a page with no engine-specific surface should produce, and re-proving that on every push would cost roughly 3.4x the wall clock for a defect class this site has never yet produced. Firefox is the expensive one, at three times Chromium.

The cost that matters is not runner minutes, though. This pipeline gates a deployment signal, which is why `external`-marked tests are already deselected from it: a verdict on this site must not turn on whether a third party answers. Adding engines re-admits that same class of unrelated red, as engine-specific timing flake, into the one signal that is supposed to mean "this deploy is good".

Firefox and WebKit stay one flag away for local verification, and the figures above are refreshed when the pins move. Worth revisiting if the site adopts CSS with uneven support, or if a Safari-specific defect is ever reported.

If the matrix is ever built, two details decide whether it answers the question it is meant to answer. Each engine must run as its own single-engine job with `fail-fast: false`, so a red engine cannot cancel its siblings and erase the comparison. And the deployment gate must run **once**, upstream of the matrix, publishing the settled `ETag` for each engine to re-check before it starts: three jobs gating independently can settle on different deployments, at which point a difference between two engines may be content drift rather than an engine defect - the failure this suite's deployment gate already exists to prevent, reappearing one level up.

Selecting more than one engine collects every browser-scoped test once per engine, so the totals describe a multi-engine run rather than the single-engine suite the site quotes. `test_published_suite_size.py` skips itself in that case rather than reporting drift that is not there.

> `--browser` is intentionally absent from `pytest.ini`. `pytest-playwright` treats the flag as repeatable, so a value in `addopts` would be additive rather than overridable: `--browser=firefox` would run Chromium *and* Firefox. Chromium is already the plugin default, so omitting it keeps the default run identical while letting the command line select the engine outright.

---

## Configuration

<sub>v1.2.0 &middot; 2026-08-12</sub>

All configuration is read once, at session start, by `config.settings.Settings`. Test modules never read `os.environ`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BASE_URL` | `https://apolskiy.github.io/` | Application under test |
| `EXPECT_TIMEOUT_MS` | `10000` | Ceiling for auto-retrying web-first assertions |
| `AI_DIAGNOSTICS_ENABLED` | `false` | Master switch for Claude failure triage |
| `ANTHROPIC_API_KEY` | *(unset)* | Credential for the diagnostics hook |
| `CLAUDE_MODEL` | `claude-opus-5` | Model used for failure triage |

Diagnostics activate only when `AI_DIAGNOSTICS_ENABLED` is truthy **and** a key is present, so a fork without secrets runs green.

Two prompt inputs are bounded in `config/settings.py` rather than by environment, since they cap token spend rather than describe an environment: `MAX_DOM_SNAPSHOT_CHARS` (40,000) and `MAX_DIAGNOSTICS_CHARS` (8,000). The log gets the smaller budget because it is already a summary - but it is not bounded by the page, and a request loop or a script erroring on every frame can produce thousands of near-identical lines. Either input that is shortened carries a note saying so, so the model never reasons over a fragment believing it has the whole; reporting that something is absent when it was merely cut off is the failure mode a silent truncation invites.

---

## Test Design Principles

<sub>v1.2.0 &middot; 2026-08-12</sub>

**Locators.** Accessible locators (`get_by_role`, `get_by_text`) are used wherever the markup exposes a role or an accessible name. The application ships no `data-testid` attributes, so the tab panels - plain `<div>` elements carrying only an `id` - are addressed by a flat `#id` selector. Structural chains such as `div > ul > li:nth-child(2)` are never used.

**Synchronization.** There are no `wait_for_timeout` calls anywhere in the suite. The page decorates itself from a `DOMContentLoaded` listener, and readiness is expressed as an exact web-first assertion: the suite waits for the `span.enc-link` placeholder collection to drain to zero. Layout measurements settle the DOM with a visibility assertion before reading any bounding box.

**Assertions.** Checks that depend on DOM internals invisible to a test author - the `active` class toggled by the SPA router, the `mailto:` payload produced by the anti-scraping decoder - are published by the Page Object as `expect_*` helpers built on Playwright's retrying assertions. Everything else is exposed as a `Locator` so tests assert on it directly.

**Isolation.** Every test gets its own browser context with an explicit viewport, so tests can run in any order without cookie, storage, or window-size bleed.

**Third parties never decide a verdict.** A test on the deployment path may observe a third party but may not fail because of one. That rule is usually served by the `external` marker, but a marker only covers a dependency a test takes deliberately - it does nothing about one arriving through a sub-resource the page happens to embed. The error-log assertions are therefore scoped by origin rather than marked, which is the same rule enforced one level down.

**Diagnostics are collected always and reported only on failure.** Recording costs nothing and cannot be retrofitted after the fact, since a browser event that predates its listener is simply gone; writing artifacts costs disk and attention, so nothing is written for a test that passed. The two decisions are independent and are made separately.

---

## Dynamic Site Discovery

<sub>v1.2.0 &middot; 2026-08-12</sub>

`utils/site_crawler.py` implements `SiteMapCrawler`, an asynchronous breadth-first Playwright crawler.

It renders each page in a real browser rather than fetching raw HTML - **this is required, not a preference**: the site publishes every outbound link as a base64 payload that only becomes an `<a href>` after its `DOMContentLoaded` script runs, so a `requests`-based crawler would discover nothing.

**Discovery rules**

| Accepted | Rejected |
| --- | --- |
| Relative paths (`/about`) | External hosts |
| Bare fragments (`#projects`), resolved against the current page | `mailto:`, `tel:`, `javascript:`, `data:`, `file:`, `ftp:` |
| Internal absolute URLs | Assets: `.pdf`, `.zip`, `.png`, `.css`, `.js`, fonts, media, Office documents |

URLs are canonicalized before use, so an empty path and `/` collapse to one route: the site links to itself both ways, which would otherwise produce a duplicate. Traversal is bounded by `max_depth` (3) and `max_pages` (50) so a link cycle cannot hang collection, and a route that fails to navigate is still recorded with `status_code: 0` rather than vanishing.

**Artifact**: `reports/sitemap.json`. Route records carry exactly the four specified fields; the surrounding envelope adds crawl context and any unhandled JavaScript exceptions caught via `pageerror` during the walk:

```json
{
  "base_url": "https://apolskiy.github.io/",
  "generated_at": "2026-07-29T06:07:33+00:00",
  "route_count": 1,
  "routes": [
    { "url": "https://apolskiy.github.io/", "parent_route": "", "discovered_at": "...", "status_code": 200 }
  ],
  "javascript_errors": []
}
```

**Parameterization**: `tests/test_dynamic_routes.py` implements `pytest_generate_tests`, which resolves the route list once per session (memoized, since the hook fires per test function) and parameterizes six health checks across it: HTTP 200, a clean first-party console/network/JavaScript log, a visible and non-empty DOM root, a meta description within usable length bounds, and no horizontal overflow at either viewport. Test ids are the route paths, so a failure reads as `test_route_responds_with_http_200[/about.html-chromium]`.

```bash
python -m pytest                        # re-crawls during collection
python -m pytest --use-cached-sitemap   # reuses reports/sitemap.json
```

CI should re-crawl so a newly published page is discovered; the cache flag is a local-iteration convenience.

> **Current scope:** the tab router uses `<li data-tab>` elements rather than anchors, so the index contributes a single route; the standalone case-study page is a genuine second document reached by an ordinary relative link. Discovery therefore yields **two** routes today and the twelve dynamic tests they generate, which is the engine working against real pages rather than a fixture. Publishing the case-study page is what proved it: the route was discovered and its full set of cases appeared with no test edit. A deliberately broken link, tried during development, produced a failing `HTTP 404` check naming the parent route it was found from.

---

## Reporting

<sub>v1.2.0 &middot; 2026-08-12</sub>

```bash
python -m pytest                       # writes allure-results/ and reports/
allure serve allure-results            # interactive Allure report
```

Every test carries `@allure.epic`, `@allure.feature`, `@allure.story`, and `@allure.severity`, and each phase is wrapped in an `allure.step` - including the steps emitted by the Page Object itself, so the report reads as a narrative of the user journey rather than a list of clicks.

On failure the suite attaches:

1. The **browser's error log** for that page - a count by category, then the events themselves, split into what this site is answerable for and what a third party is. Attached whether or not the failing test asserted on it, and attached first: the events are already in memory, so this is the one piece of evidence that survives a page which has closed under the test.
2. A full-page **screenshot** at the moment of failure.
3. The fully rendered **DOM snapshot**, including script-injected nodes.
4. A **Playwright trace** (`reports/traces/`) with screenshots and DOM snapshots per step, openable in the Trace Viewer.
5. A **Claude root-cause analysis**: verdict (`application regression` / `test defect` / `environment flake` / `inconclusive`), the evidence behind it drawn from both the error log and the DOM and labelled with which it came from, the probable cause, and a suggested fix.

The error log is additionally published as a pytest report section, so it appears beneath the traceback in the terminal, in the CI log, and in `reports/pytest-report.html`. Allure is the richer report but not always the one being read, and a diagnostic nobody opens is not a diagnostic.

The diagnostics hook is strictly advisory. A missing credential, a network failure, or an API error is logged as a warning and degrades to "no report": it never converts a product failure into an infrastructure failure, and never masks the real Playwright error.

---

## Test Identity

<sub>v1.3.0 &middot; 2026-08-16</sub>

Every test carries an assigned, stable identifier:

```python
@pytest.mark.test_id("PAWA_10001")
def test_footer_owner_link_shares_the_table_hover_color(...) -> None:
```

IDs run from `PAWA_10001` and are **never reused** - deleting a test retires
its number rather than freeing it. The suite currently occupies `PAWA_10001`
to `PAWA_10042`; the next free identifier is `PAWA_10043`.

The identifier exists because **a test's name is not a stable identity**. Any
store keyed on the name forks a test's history the moment it is renamed, turning
one test with a long record into two with short ones - silently, since both
halves still look like valid tests. Names should stay free to improve, and this
is what makes that free.

`conftest.py` republishes the marker into both report formats at collection
time, in `_publish_test_ids`: as an Allure label and as a JUnit `<property>`.
Collection time rather than a fixture, so the label is attached before any
reporter starts building a result and cannot be lost to fixture ordering.

The consumer is
[PortfolioTestInsights](https://github.com/apolskiy/PortfolioTestInsights),
which keeps this suite's results past GitHub's 90-day artifact retention. It
keys on `COALESCE(test_id, test_uid)`, so history recorded before the IDs
existed still stitches to history recorded after.

## Static Analysis

<sub>v1.0.0 &middot; 2026-08-10</sub>

```bash
python -m pylint config pages utils tests conftest.py
```

The suite is held at **10.00/10**, and CI runs the same command with `--fail-under=10` before any browser starts. `.pylintrc` rejects one- and two-character identifiers outright rather than allowing the usual `i`/`x`/`df` escape hatches. Only two checks are disabled, each for a documented reason: `redefined-outer-name` (the pytest fixture idiom) and `duplicate-code` (test suites intentionally repeat arrange/assert shapes).

---

## Defect Found and Fixed

<sub>v1.0.0 &middot; 2026-08-10</sub>

`test_mobile_layout_has_no_horizontal_overflow` caught a real mobile layout bug on its first run: at a 390px viewport the document measured **398px**, and one tab reached **400px**. Two independent causes in the `max-width: 600px` block of `css/apolskiybiz.css`:

1. **Profile header (all tabs, +8px).** `#profile-header table.layout td` was set to `display: block; width: 100%` but never given `box-sizing: border-box`, so the scoped 10px horizontal cell padding was added *on top of* the 100% width. The stacked data-table cells in the same media query already declared `box-sizing`; the profile-header cells were missed.
2. **HTTP Emulators tab (+10px).** Long unbreakable tokens - source filenames such as `custom_header_response_to_http_request.py` - set the table's intrinsic minimum content width, and a `<table>` box grows to that minimum regardless of `width: 100%`.

Both are fixed in the site repository (`apolskiy/apolskiy.github.io`). The second needed `overflow-wrap: anywhere` specifically: `break-word` permits a mid-word break but does **not** reduce the intrinsic min-content size that the table is sized from, so it would not have shrunk the table.

Verified clean afterwards on every tab at 320px, 390px, and 600px, on both Chromium and Firefox.

> Both fixes are live: `css/apolskiybiz.css` now carries `box-sizing: border-box` on the stacked profile-header cells and `overflow-wrap: anywhere` on the project tables, and the test passes against the deployed site.

---

## Coverage Summary

<sub>v1.2.0 &middot; 2026-08-12</sub>

| Suite | Scenarios | Focus |
| --- | --- | --- |
| `test_navigation.py` | 13 | Title, profile header, self-hosted portrait, footer, default tab, per-tab panel exclusivity (one case per tab), tab deselection, persistent chrome, skills matrix |
| `test_engineering_outcomes.py` | 10 | Outcomes table renders, every claim cites a project, each citation opens the tab it names (one case per project), emphasis rendering does not fracture a sentence, row-hover parity, keyboard activation |
| `test_responsive.py` | 7 | Tab-strip wrapping, header suppression below the breakpoint, horizontal overflow on both viewports (every tab checked inside each case), stacked profile header |
| `test_link_obfuscation.py` | 7 | Placeholder decoding, safe URL schemes, outbound link-rot detection, `noopener noreferrer` hardening, address never rendered as text, copyright owner link, `noscript` fallback |
| `test_link_styling.py` | 1 | Copyright link shares the table hover color, and hovering visibly changes it |
| `test_project_panels.py` | 20 | Per project panel: a Documentation row linking that project's README, decoded to an absolute target and opening in a hardened new tab; a CI badge sourced from that project's own repository and carrying alt text; and the repository row, badge source and README target all reduced to `owner/name` and required to agree |
| `test_published_image_claims.py` | 1 | The published `apolskiy/flask_app` image installs Flask's dependency closure and nothing beyond it |
| `test_published_suite_size.py` | 2 | The suite-size figures quoted on the Web Automation tab and in the CI case study match the suite that is running |
| `test_runtime_health.py` | 1 | Walking every tab in sequence leaves the browser's error log clean - the load-time checks below never exercise the router or the decoder, because neither runs until something is clicked |
| `test_dynamic_routes.py` | 6 × routes | Per discovered route: HTTP 200, first-party console/network/JS error log, visible DOM root, a meta description within usable length bounds, desktop and mobile overflow |

**78 tests on the deployment path, plus 2 that run weekly - 80 in total**, collected against the live site today (6 dynamic × 2 discovered routes) and growing automatically as pages are published and as navigation tabs are added.

The deployment pipeline runs `pytest -m "not external"`, which is the 78, depending on nothing but this site. The two `external` tests reach third parties - one resolves outbound links, the other reads the published container image - and run weekly via `external-links.yml`, or on demand with `pytest -m external`.

Three suites grow on their own, all from the same declaration. `test_navigation.py` parameterizes over `NavigationTab`, so publishing any tab adds a case; `test_project_panels.py` and `test_engineering_outcomes.py` parameterize over the subset of those tabs that describe a project, contributing four cases and one respectively. The counts above already include the VM Cluster Deployment tab, which added five of them without a test edit.
