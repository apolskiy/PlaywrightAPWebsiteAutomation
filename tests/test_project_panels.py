"""Completeness coverage for the four project panels.

Each project tab is a table describing one repository, and the rows are written
by hand per project. That makes an omission the likely failure: a panel ships
without the row its siblings all carry, and nothing notices, because every
individual assertion elsewhere in the suite still passes.

These tests assert the property across every project at once, so a new project
tab is held to the same contract the existing ones meet rather than inheriting
whatever its author remembered to include.
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Project Panel Completeness"

#: The tabs that describe a single repository. Home and Engineering Outcomes are
#: cross-project index pages and carry no project table of their own.
PROJECT_TABS: tuple[NavigationTab, ...] = (
    NavigationTab.REST_API,
    NavigationTab.PORTFOLIO_WEBSITE,
    NavigationTab.WEB_AUTOMATION,
    NavigationTab.HTTP_EMULATORS,
)

#: Accepted spellings of a README target, lower-cased before comparison. The
#: site links a mix of `README.md` and `readme.md` because the repositories
#: themselves are inconsistent, and that is the repositories' business.
README_SUFFIXES = ("readme.md",)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every project panel links its own documentation")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_project_panel_publishes_a_documentation_link(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """A project panel must carry a Documentation row pointing at its README.

    A reader who wants depth on a project has exactly one next step from the
    panel, and it is this link. A panel missing it is a dead end.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    documentation_link = landing_page.documentation_link(project_tab)

    with allure.step("Verify the Documentation row publishes exactly one link"):
        expect(documentation_link).to_have_count(1)
        expect(documentation_link).to_be_visible()

    with allure.step("Verify the link was decoded into an absolute https target"):
        href = documentation_link.get_attribute("href") or ""
        allure.attach(
            href, name="Documentation target", attachment_type=allure.attachment_type.TEXT
        )
        assert href.startswith("https://"), (
            f"The {project_tab.label} documentation link resolved to '{href}'. "
            "The base64 placeholder either failed to decode or was encoded "
            "with a relative target."
        )

    with allure.step("Verify the link points at a README rather than a repository root"):
        assert href.lower().endswith(README_SUFFIXES), (
            f"The {project_tab.label} documentation link points at '{href}', "
            "which is not a README. The Documentation row should reach the "
            "prose, not the file listing."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every project panel publishes a build-status badge")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("project_tab", PROJECT_TABS, ids=lambda tab: tab.name.lower())
def test_project_panel_publishes_a_ci_status_badge(
    desktop_page: LandingPage, project_tab: NavigationTab
) -> None:
    """A project panel must carry a CI badge sourced from its own repository.

    The badge is the one element on the page that reports whether the project
    currently works. A panel without one asks the reader to take the project's
    health on trust, and a badge pointing at the wrong repository is worse
    still: it reports a green that belongs to someone else.

    The assertion deliberately inspects the ``src`` rather than waiting for the
    image to render. Badge images are fetched from github.com, and a deploy
    signal must not depend on that host being reachable from the runner.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        project_tab: The project panel under inspection.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(project_tab)

    badge = landing_page.ci_status_badge(project_tab)

    with allure.step("Verify the CI row publishes exactly one badge"):
        expect(badge).to_have_count(1)

    with allure.step("Verify the badge is served from a GitHub Actions endpoint"):
        source = badge.get_attribute("src") or ""
        allure.attach(
            source, name="Badge source", attachment_type=allure.attachment_type.TEXT
        )
        assert source.startswith("https://github.com/apolskiy/"), (
            f"The {project_tab.label} badge is sourced from '{source}', which is "
            "not one of this author's repositories."
        )
        assert "/badge.svg" in source, (
            f"The {project_tab.label} badge source '{source}' is not a status "
            "badge endpoint."
        )

    with allure.step("Verify the badge carries alternative text"):
        alt_text = badge.get_attribute("alt") or ""
        assert alt_text.strip(), (
            f"The {project_tab.label} badge has no alt text, so its status is "
            "invisible to a screen reader and to anyone whose images fail."
        )


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

    documentation_link = landing_page.documentation_link(project_tab)

    with allure.step("Verify the link targets a new browsing context"):
        expect(documentation_link).to_have_attribute("target", "_blank")

    with allure.step("Verify the new tab is hardened against reverse tabnabbing"):
        rel = documentation_link.get_attribute("rel") or ""
        missing = [token for token in ("noopener", "noreferrer") if token not in rel]
        assert not missing, (
            f"The {project_tab.label} documentation link opens a new tab with "
            f"rel='{rel}', missing {missing}. The placeholder is likely lacking "
            "its 'data-nw' attribute."
        )
