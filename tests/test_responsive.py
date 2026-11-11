"""Tests the landing page layout on both sides of the site's 600px breakpoint.

Created: 2026-07-28
Last updated: 2026-11-10

This file covers seven behaviors, the visible consequences of the site's one
``max-width: 600px`` media query. At 1920x1080 the tab strip stays on one row,
the skills matrix keeps its column headers, and no tab overflows sideways. At
390x844 the tab strip wraps, the matrix headers are hidden, no tab overflows
sideways, and the stacked profile header keeps its portrait, name and footer.

The cases run on the deployment path. A failure means the stylesheet's
breakpoint rules regressed, so the page renders the wrong layout at that width
or scrolls sideways for a reader. The two overflow cases iterate
``NavigationTab`` inside one case each, so a new tab widens their coverage
without adding a case.

Specified by ``README.md`` sections "Key Features" (Cross-Viewport Coverage),
"Defect Found and Fixed" and "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Responsive Cross-Viewport Layout"


@pytest.mark.test_id("PAWA_10035")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The desktop tab strip renders on a single row")
@allure.severity(allure.severity_level.CRITICAL)
def test_desktop_navigation_renders_on_a_single_row(desktop_page: LandingPage) -> None:
    """Assert the flex tab strip stays on one row at 1920x1080.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the navigation landmark is displayed"):
        expect(landing_page.nav_bar()).to_be_visible()

    with allure.step("Verify every tab shares one horizontal row"):
        assert landing_page.navigation_row_count() == 1, (
            "The desktop tab strip wrapped onto more than one row, which means "
            "the shrink-to-fit menu width regressed."
        )


@pytest.mark.test_id("PAWA_10036")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The desktop skills matrix keeps its column headers")
@allure.severity(allure.severity_level.NORMAL)
def test_desktop_skills_matrix_shows_column_headers(desktop_page: LandingPage) -> None:
    """Assert the skills matrix header row is visible above the breakpoint.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the header row of the skills matrix is displayed"):
        expect(landing_page.skills_matrix_header_row()).to_be_visible()


@pytest.mark.test_id("PAWA_10037")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The desktop layout never scrolls sideways")
@allure.severity(allure.severity_level.NORMAL)
def test_desktop_layout_has_no_horizontal_overflow(desktop_page: LandingPage) -> None:
    """Assert no tab makes the document wider than the desktop viewport.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    for navigation_tab in NavigationTab:
        with allure.step(f"Verify '{navigation_tab.label}' fits the desktop viewport"):
            landing_page.open_tab(navigation_tab)
            assert not landing_page.has_horizontal_overflow(), (
                f"The '{navigation_tab.label}' panel overflows the desktop viewport "
                f"horizontally ({landing_page.document_scroll_width()}px wide)."
            )


@pytest.mark.test_id("PAWA_10038")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The mobile tab strip wraps onto multiple rows")
@allure.severity(allure.severity_level.CRITICAL)
def test_mobile_navigation_wraps_onto_multiple_rows(mobile_page: LandingPage) -> None:
    """Assert the tab strip wraps onto more than one row below the breakpoint.

    Args:
        mobile_page (LandingPage): The landing Page Object at 390x844.

    Returns:
        None
    """
    landing_page = mobile_page.navigate()

    with allure.step("Verify the navigation landmark is displayed"):
        expect(landing_page.nav_bar()).to_be_visible()

    with allure.step("Verify the tab strip occupies more than one row"):
        assert landing_page.navigation_row_count() > 1, (
            "The mobile tab strip stayed on a single row, so 'flex-wrap: wrap' "
            "is no longer being applied below the 600px breakpoint."
        )


@pytest.mark.test_id("PAWA_10039")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The mobile layout hides the redundant matrix headers")
@allure.severity(allure.severity_level.NORMAL)
def test_mobile_skills_matrix_hides_column_headers(mobile_page: LandingPage) -> None:
    """Assert the skills matrix renders with its header row hidden below the breakpoint.

    Once rows stack vertically the column headers add nothing.

    Args:
        mobile_page (LandingPage): The landing Page Object at 390x844.

    Returns:
        None
    """
    landing_page = mobile_page.navigate()

    with allure.step("Verify the skills matrix itself is still rendered"):
        expect(landing_page.skills_matrix()).to_be_visible()

    with allure.step("Verify the tabular header row is suppressed"):
        expect(landing_page.skills_matrix_header_row()).to_be_hidden()


@pytest.mark.test_id("PAWA_10040")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The mobile layout never scrolls sideways")
@allure.severity(allure.severity_level.CRITICAL)
def test_mobile_layout_has_no_horizontal_overflow(mobile_page: LandingPage) -> None:
    """Assert no tab makes the document wider than the 390px mobile viewport.

    Args:
        mobile_page (LandingPage): The landing Page Object at 390x844.

    Returns:
        None
    """
    landing_page = mobile_page.navigate()

    for navigation_tab in NavigationTab:
        with allure.step(f"Verify '{navigation_tab.label}' fits the mobile viewport"):
            landing_page.open_tab(navigation_tab)
            assert not landing_page.has_horizontal_overflow(), (
                f"The '{navigation_tab.label}' panel overflows the mobile viewport "
                f"horizontally ({landing_page.document_scroll_width()}px wide)."
            )


@pytest.mark.test_id("PAWA_10041")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The mobile profile header stacks without losing content")
@allure.severity(allure.severity_level.NORMAL)
def test_mobile_profile_header_remains_complete(mobile_page: LandingPage) -> None:
    """Assert the stacked profile header keeps the portrait, name and footer visible.

    Args:
        mobile_page (LandingPage): The landing Page Object at 390x844.

    Returns:
        None
    """
    landing_page = mobile_page.navigate()

    with allure.step("Verify the portrait and name survive the stacked layout"):
        expect(landing_page.profile_photo()).to_be_visible()
        expect(landing_page.profile_heading()).to_be_visible()

    with allure.step("Verify the footer is still reachable at the mobile width"):
        expect(landing_page.site_footer()).to_be_visible()
