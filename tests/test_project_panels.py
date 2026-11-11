"""Tests that every project panel is complete and describes only its own repositories.

Created: 2026-07-30
Last updated: 2026-11-10

This file covers four behaviors, each parameterized over every project tab: a
panel publishes one README link per repository it declares, decoded to an
absolute ``https`` target; it publishes at least one CI status badge per
repository, each from this account and carrying alt text; its Repo,
Documentation and badge rows all reduce to exactly the repositories it declares;
and its documentation links open in a new tab hardened with
``noopener noreferrer``. The private ``_attribute_values`` helper normalizes
attribute reads.

The cases run on the deployment path against the desktop landing page. A
failure means a panel shipped missing a row its siblings carry, or still names
a repository it was copied from, so a reader of that panel is sent to, or shown
the build health of, the wrong project.

**The contract is per declared repository.** ``PROJECT_REPOSITORIES`` lists the
repositories each panel describes, one for most projects and two for Multi-LLM
Evaluation, whose harness and test cases live in separate repositories so each
can change without destabilizing the other. A panel must cover every repository
it declares and cite none it does not. A new project tab is held to the same
contract by being added there.

**The Documentation row is a reader's one way in.** A panel without it, or with
one link for two repositories, leaves part of the project with no route to its
prose, so each link must reach a README rather than a repository root. Off-site
targets open in a new tab so the reader keeps their place, and ``rel`` must
close the reverse-tabnabbing exposure ``target="_blank"`` opens.

**Badges are read by ``src``, never rendered**, because the images are served
by github.com and the verdict may not depend on a third party.

Specified by ``README.md`` sections "Key Features" (Panels Checked Against
Themselves), "Test Design Principles" and "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab, github_repository

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Project Panel Completeness"

#: DECLARED REPOSITORIES (two per panel allowed since 2026-11-10). The
#: repositories each project tab describes, lower-cased ``owner/name``, in the
#: order the panel lists them. Home and Engineering Outcomes are cross-project
#: index pages and carry no project table.
PROJECT_REPOSITORIES: dict[NavigationTab, tuple[str, ...]] = {
    NavigationTab.REST_API: ("apolskiy/countryweather",),
    NavigationTab.PORTFOLIO_WEBSITE: ("apolskiy/apolskiy.github.io",),
    NavigationTab.WEB_AUTOMATION: ("apolskiy/playwrightapwebsiteautomation",),
    NavigationTab.HTTP_EMULATORS: ("apolskiy/publicap",),
    NavigationTab.VM_CLUSTER: ("apolskiy/vm-deployment-and-configuration",),
    NavigationTab.TEST_INSIGHTS: ("apolskiy/portfoliotestinsights",),
    NavigationTab.LLM_EVALUATION: ("apolskiy/ap-harness-qc", "apolskiy/ap-model-qc"),
}

#: PARAMETERS. The project tabs, in navigation order.
PROJECT_TABS: tuple[NavigationTab, ...] = tuple(PROJECT_REPOSITORIES)

#: CASE-BLIND, decided 2026-07-30. Accepted endings of a README target, matched
#: lower-cased: the site links both ``README.md`` and ``readme.md`` because the
#: repositories themselves differ, and that is the repositories' business.
README_SUFFIXES = ("readme.md",)


def _attribute_values(locator_values: list[str | None]) -> list[str]:
    """Return attribute reads with a missing attribute turned into an empty string.

    Args:
        locator_values (list[str | None]): Raw ``get_attribute`` results, one
            per element.

    Returns:
        list[str]: The same values with None replaced by ``""``.
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
    """Assert a panel carries one visible README link per repository it declares.

    Each link must be decoded to an absolute ``https`` target ending in
    ``readme.md``, in any case.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        project_tab (NavigationTab): The project panel under inspection.

    Returns:
        None
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
    """Assert a panel carries at least one CI status badge per declared repository.

    A panel describing a chain of workflows may carry one badge per gate. Every
    badge ``src`` must start with ``https://github.com/apolskiy/`` and contain
    ``/badge.svg``, and every badge must carry alt text. The ``src`` is read,
    not rendered.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        project_tab (NavigationTab): The project panel under inspection.

    Returns:
        None
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
    """Assert a panel's repository, documentation and badge rows name its repositories.

    Every target must reduce to an ``owner/name``. The Repo and Documentation
    rows must name exactly the declared repositories, in the declared order;
    every badge must come from one of them, and each declared repository must
    report at least one badge. Why the per-row checks alone pass on a panel
    copied from a sibling: ``README.md`` section "Key Features" (Panels Checked
    Against Themselves).

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        project_tab (NavigationTab): The project panel under inspection.

    Returns:
        None
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
    """Assert every documentation link opens a new tab with ``noopener noreferrer``.

    The row must publish at least one link, and each must carry
    ``target="_blank"`` and both ``rel`` tokens.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        project_tab (NavigationTab): The project panel under inspection.

    Returns:
        None
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
