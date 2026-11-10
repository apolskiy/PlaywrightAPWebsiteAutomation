"""Completeness and internal-consistency coverage for the project panels.

Each project tab is a table describing one project, and the rows are written by
hand per project. That makes two failures likely. The first is omission: a
panel ships without the row its siblings all carry, and nothing notices, because
every individual assertion elsewhere in the suite still passes. The second
arrives with the panel that was started by copying a sibling - the rows are all
present, all well-formed, and one of them still names the repository it was
copied from.

Most projects live in one repository, but not all: the Multi-LLM Evaluation
project is a harness and its test cases, split into two repositories so each
can change without destabilizing the other, and its panel describes both. So
the contract is stated against the repositories each panel declares rather than
against "one repository per panel" - a panel must cover every repository it
declares, and must not cite one it does not.

These tests assert the properties across every project at once, so a new project
tab is held to the same contract the existing ones meet rather than inheriting
whatever its author remembered to change.
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab, github_repository

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Project Panel Completeness"

#: The repositories each project tab describes, lower-cased ``owner/name``, in
#: the order the panel lists them. Home and Engineering Outcomes are
#: cross-project index pages and carry no project table of their own.
PROJECT_REPOSITORIES: dict[NavigationTab, tuple[str, ...]] = {
    NavigationTab.REST_API: ("apolskiy/countryweather",),
    NavigationTab.PORTFOLIO_WEBSITE: ("apolskiy/apolskiy.github.io",),
    NavigationTab.WEB_AUTOMATION: ("apolskiy/playwrightapwebsiteautomation",),
    NavigationTab.HTTP_EMULATORS: ("apolskiy/publicap",),
    NavigationTab.VM_CLUSTER: ("apolskiy/vm-deployment-and-configuration",),
    NavigationTab.TEST_INSIGHTS: ("apolskiy/portfoliotestinsights",),
    NavigationTab.LLM_EVALUATION: ("apolskiy/ap-harness-qc", "apolskiy/ap-model-qc"),
}

#: The project tabs, in navigation order, for parametrization.
PROJECT_TABS: tuple[NavigationTab, ...] = tuple(PROJECT_REPOSITORIES)

#: Accepted spellings of a README target, lower-cased before comparison. The
#: site links a mix of `README.md` and `readme.md` because the repositories
#: themselves are inconsistent, and that is the repositories' business.
README_SUFFIXES = ("readme.md",)


def _attribute_values(locator_values: list[str | None]) -> list[str]:
    """Normalize attribute reads, turning a missing attribute into an empty string.

    Args:
        locator_values: Raw ``get_attribute`` results, one per element.

    Returns:
        The same values with ``None`` replaced by ``""``.
    """
    return [value or "" for value in locator_values]


@pytest.mark.test_id("PAWA_10028")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every project panel links its own documentation")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_project_panel_publishes_a_documentation_link(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """A project panel must carry one README link per repository it describes.

    A reader who wants depth on a project has exactly one next step from the
    panel, and it is this row. A panel missing it is a dead end, and a panel
    describing two repositories but documenting one leaves half the project
    without a way in.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    expected_count = len(PROJECT_REPOSITORIES[project_tab])
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    documentation_links = landing_page.documentation_link(project_tab)

    with allure.step(f"Verify the Documentation row publishes {expected_count} link(s)"):
        expect(documentation_links).to_have_count(expected_count)
        for link_index in range(expected_count):
            expect(documentation_links.nth(link_index)).to_be_visible()

    hrefs = _attribute_values(
        [documentation_links.nth(index).get_attribute("href") for index in range(expected_count)]
    )
    allure.attach(
        "\n".join(hrefs), name="Documentation targets", attachment_type=allure.attachment_type.TEXT
    )

    with allure.step("Verify every link was decoded into an absolute https target"):
        relative = [href for href in hrefs if not href.startswith("https://")]
        assert not relative, (
            f"The {project_tab.label} documentation links {relative} are not absolute "
            "https targets. The base64 placeholder either failed to decode or was "
            "encoded with a relative target."
        )

    with allure.step("Verify every link points at a README rather than a repository root"):
        not_readme = [href for href in hrefs if not href.lower().endswith(README_SUFFIXES)]
        assert not not_readme, (
            f"The {project_tab.label} documentation links {not_readme} are not "
            "READMEs. The Documentation row should reach the prose, not the file "
            "listing."
        )


@pytest.mark.test_id("PAWA_10029")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every project panel publishes a build-status badge")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_project_panel_publishes_a_ci_status_badge(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """A project panel must carry CI badges sourced from its own repositories.

    The badge is the one element on the page that reports whether the project
    currently works. A panel without one asks the reader to take the project's
    health on trust. A panel describing a chain of workflows may carry one
    badge per gate in the chain, but every one of them must be a real status
    badge with alternative text.

    The assertion deliberately inspects the ``src`` rather than waiting for the
    image to render. Badge images are fetched from github.com, and a deploy
    signal must not depend on that host being reachable from the runner.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    badges = landing_page.ci_status_badge(project_tab)

    with allure.step("Verify the CI row publishes at least one badge per repository"):
        badge_count = badges.count()
        assert badge_count >= len(PROJECT_REPOSITORIES[project_tab]), (
            f"The {project_tab.label} CI row carries {badge_count} badge(s) for "
            f"{len(PROJECT_REPOSITORIES[project_tab])} repositories, so at least one "
            "repository's build health is not shown."
        )

    sources = _attribute_values(
        [badges.nth(index).get_attribute("src") for index in range(badge_count)]
    )
    alt_texts = _attribute_values(
        [badges.nth(index).get_attribute("alt") for index in range(badge_count)]
    )
    allure.attach(
        "\n".join(sources), name="Badge sources", attachment_type=allure.attachment_type.TEXT
    )

    with allure.step("Verify every badge is served from a GitHub Actions endpoint"):
        foreign = [
            source for source in sources if not source.startswith("https://github.com/apolskiy/")
        ]
        assert not foreign, (
            f"The {project_tab.label} badges {foreign} are not sourced from one of "
            "this author's repositories."
        )
        not_badges = [source for source in sources if "/badge.svg" not in source]
        assert not not_badges, (
            f"The {project_tab.label} badge sources {not_badges} are not status "
            "badge endpoints."
        )

    with allure.step("Verify every badge carries alternative text"):
        unlabelled = [source for source, alt in zip(sources, alt_texts) if not alt.strip()]
        assert not unlabelled, (
            f"The {project_tab.label} badges {unlabelled} have no alt text, so their "
            "status is invisible to a screen reader and to anyone whose images fail."
        )


@pytest.mark.test_id("PAWA_10030")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every row of a project panel names the repositories it declares")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_project_panel_rows_agree_on_its_repositories(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """A panel's repositories, badges, and READMEs must belong to the same project.

    Each of those rows is asserted elsewhere, and each of those assertions
    passes on a panel that is quietly describing a different project. The badge
    check only requires a source under this author's account, which is true of
    every repository he owns, so a panel begun by copying a sibling can keep the
    sibling's badge and stay green - reporting a build result that belongs to
    someone else, on the one row of the page whose entire purpose is to say
    whether this project currently works.

    Nothing about that is visible from the rendered page: the badge draws, the
    links resolve, and the reader has no way to know the green is unrelated. It
    is caught by comparing every row against the repositories the panel
    declares: the Repo and Documentation rows must name exactly those, in the
    declared order, and every badge must come from one of them, with each
    declared repository reporting at least one.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    declared = PROJECT_REPOSITORIES[project_tab]
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    with allure.step("Read the repositories named by each row"):
        targets: dict[str, list[str]] = {}
        for row_name, locator, attribute in (
            ("Repo row", landing_page.repository_link(project_tab), "href"),
            ("Documentation", landing_page.documentation_link(project_tab), "href"),
            ("CI badges", landing_page.ci_status_badge(project_tab), "src"),
        ):
            targets[row_name] = _attribute_values(
                [locator.nth(index).get_attribute(attribute) for index in range(locator.count())]
            )
        repositories = {
            row_name: [github_repository(target) for target in row_targets]
            for row_name, row_targets in targets.items()
        }
        allure.attach(
            "\n".join(f"{row_name}: {row_targets}" for row_name, row_targets in targets.items()),
            name=f"{project_tab.label} targets",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify every target resolved to an identifiable repository"):
        unresolved = {
            row_name: [target for target, repo in zip(targets[row_name], repos) if not repo]
            for row_name, repos in repositories.items()
        }
        unresolved = {row_name: found for row_name, found in unresolved.items() if found}
        assert not unresolved, (
            f"On the {project_tab.label} panel these targets do not name a GitHub "
            f"repository: {unresolved}."
        )

    with allure.step(f"Verify the Repo and Documentation rows name exactly {list(declared)}"):
        for row_name in ("Repo row", "Documentation"):
            assert tuple(repositories[row_name]) == declared, (
                f"The {project_tab.label} {row_name} names {repositories[row_name]}, "
                f"but the panel declares {list(declared)}. Every row of a panel must "
                "belong to the project the panel is about."
            )

    with allure.step("Verify every badge reports a declared repository, and each has one"):
        foreign = sorted(set(repositories["CI badges"]) - set(declared))
        assert not foreign, (
            f"The {project_tab.label} panel carries badges from {foreign}, which it "
            "does not describe - a badge left pointing at a sibling reports a green "
            "build that says nothing about this project."
        )
        unreported = [repo for repo in declared if repo not in repositories["CI badges"]]
        assert not unreported, (
            f"The {project_tab.label} panel declares {unreported} but shows no badge "
            "for it, so that repository's build health is invisible."
        )


@pytest.mark.test_id("PAWA_10031")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Documentation links open in a new tab without leaking the opener")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_documentation_link_opens_in_a_hardened_new_tab(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """Documentation links must leave the site in a new, hardened tab.

    Every one of these targets is off-site, so losing the reader's place in the
    portfolio to follow one is a needless cost. ``target="_blank"`` without
    ``rel="noopener noreferrer"`` is the reverse-tabnabbing exposure the rest of
    the suite already guards against; this pins it per project.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    documentation_links = landing_page.documentation_link(project_tab)
    link_count = documentation_links.count()

    with allure.step("Verify the row publishes a link to inspect"):
        assert link_count >= 1, (
            f"The {project_tab.label} panel publishes no documentation link, so there "
            "is nothing to check for hardening."
        )

    for link_index in range(link_count):
        documentation_link = documentation_links.nth(link_index)
        href = documentation_link.get_attribute("href") or ""

        with allure.step(f"Verify {href} targets a new browsing context"):
            expect(documentation_link).to_have_attribute("target", "_blank")

        with allure.step(f"Verify {href} is hardened against reverse tabnabbing"):
            rel = documentation_link.get_attribute("rel") or ""
            missing = [token for token in ("noopener", "noreferrer") if token not in rel]
            assert not missing, (
                f"The {project_tab.label} documentation link {href} opens a new tab "
                f"with rel='{rel}', missing {missing}. The placeholder is likely "
                "lacking its 'data-nw' attribute."
            )
