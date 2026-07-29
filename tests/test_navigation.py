"""Header integrity and single-page-application routing coverage.

Every assertion here is expressed through :class:`~pages.landing_page.LandingPage`;
this module deliberately contains no selectors and no direct Playwright page
calls, so a markup change is absorbed by the Page Object alone.
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Navigation and SPA Routing"


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The landing page publishes the site owner's identity")
@allure.severity(allure.severity_level.BLOCKER)
def test_landing_page_exposes_owner_identity(desktop_page: LandingPage) -> None:
    """The page must load with its title, portrait, name, and footer intact.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the document title advertises the technology stack"):
        landing_page.expect_title_contains("Playwright")

    with allure.step("Verify the permanent profile header is rendered"):
        expect(landing_page.profile_photo()).to_be_visible()
        expect(landing_page.profile_heading()).to_be_visible()

    with allure.step("Verify the copyright footer is rendered"):
        expect(landing_page.site_footer()).to_be_visible()


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Home is the default tab on first load")
@allure.severity(allure.severity_level.CRITICAL)
def test_home_tab_is_selected_on_first_load(desktop_page: LandingPage) -> None:
    """A cold load must land on Home with only the Home panel displayed.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the Home tab carries the router's active state"):
        landing_page.expect_tab_selected(NavigationTab.HOME)

    with allure.step("Verify every other content panel stays collapsed"):
        landing_page.expect_only_panel_visible(NavigationTab.HOME)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Each tab reveals exactly one content panel")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.parametrize(
    "selected_tab", list(NavigationTab), ids=lambda tab: tab.name.lower()
)
def test_activating_a_tab_reveals_only_its_panel(
    desktop_page: LandingPage, selected_tab: NavigationTab
) -> None:
    """Activating any tab must display its panel and hide all the others.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        selected_tab: The navigation tab exercised by this parametrisation.
    """
    landing_page = desktop_page.navigate()

    landing_page.open_tab(selected_tab)

    with allure.step("Verify the clicked tab is marked as selected"):
        landing_page.expect_tab_selected(selected_tab)

    with allure.step("Verify panel visibility is mutually exclusive"):
        landing_page.expect_only_panel_visible(selected_tab)

    with allure.step("Verify the panel renders its own heading"):
        expect(landing_page.panel_heading(selected_tab)).to_be_visible()


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Switching tabs clears the previously selected tab")
@allure.severity(allure.severity_level.NORMAL)
def test_switching_tabs_deselects_the_previous_tab(desktop_page: LandingPage) -> None:
    """The router must never leave two tabs in the active state at once.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Move away from the default Home tab"):
        landing_page.open_tab(NavigationTab.WEB_AUTOMATION)
        landing_page.expect_tab_selected(NavigationTab.WEB_AUTOMATION)
        landing_page.expect_tab_not_selected(NavigationTab.HOME)

    with allure.step("Return to Home and verify the state is handed back"):
        landing_page.open_tab(NavigationTab.HOME)
        landing_page.expect_tab_selected(NavigationTab.HOME)
        landing_page.expect_tab_not_selected(NavigationTab.WEB_AUTOMATION)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The profile header and footer persist across every tab")
@allure.severity(allure.severity_level.NORMAL)
def test_profile_header_and_footer_persist_across_tabs(desktop_page: LandingPage) -> None:
    """Chrome outside the tab container must survive every routing transition.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    for navigation_tab in NavigationTab:
        with allure.step(f"Verify the shared chrome after opening '{navigation_tab.label}'"):
            landing_page.open_tab(navigation_tab)
            expect(landing_page.profile_header()).to_be_visible()
            expect(landing_page.profile_photo()).to_be_visible()
            expect(landing_page.site_footer()).to_be_visible()


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The Home panel renders the technical skills matrix")
@allure.severity(allure.severity_level.NORMAL)
def test_home_panel_renders_the_skills_matrix(desktop_page: LandingPage) -> None:
    """The Home tab must present the skills table with both column headers.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the skills matrix is present on the default tab"):
        expect(landing_page.skills_matrix()).to_be_visible()

    with allure.step("Verify both column headers are labelled"):
        expect(landing_page.skills_matrix_column_header("Area")).to_be_visible()
        expect(
            landing_page.skills_matrix_column_header("Core Technologies & Methodologies")
        ).to_be_visible()
