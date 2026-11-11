"""Tests that the site's links share one hover color.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains one test: the copyright footer's owner link hovers to the
same color as a link in a project table, and hovering visibly changes it.

It runs on the deployment path against the landing page at the desktop
viewport. A failure means a link has drifted out of the stylesheet's shared
``a:hover`` rule, or that hovering gives the user no visible feedback.

**Compared against a table link, not a fixed color.** The stylesheet applies
one hover color across the profile header, the project tables and the footer,
so a re-theme that changes it everywhere stays green, while a rule that leaves
the shared selector list fails.

Specified by ``README.md`` section "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Interactive Link Styling"


@pytest.mark.test_id("PAWA_10020")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The copyright link shares the hover color used in the tables")
@allure.severity(allure.severity_level.NORMAL)
def test_footer_owner_link_shares_the_table_hover_color(desktop_page: LandingPage) -> None:
    """Assert the footer owner link hovers to a table link's color, and changes.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()
    footer_link = landing_page.footer_owner_link()

    with allure.step("Capture the footer link's resting color"):
        resting_color = landing_page.computed_color(footer_link)

    with allure.step("Capture the reference hover color from a project table link"):
        landing_page.open_tab(NavigationTab.REST_API)
        table_hover_color = landing_page.hover_color(
            landing_page.panel_link(NavigationTab.REST_API)
        )

    with allure.step("Verify the footer link hovers to the same color"):
        footer_hover_color = landing_page.hover_color(footer_link)
        assert footer_hover_color == table_hover_color, (
            "The copyright link does not share the site's hover color: it "
            f"resolves to {footer_hover_color} while a project-table link "
            f"resolves to {table_hover_color}. The footer selector is likely "
            "missing from the shared 'a:hover' rule."
        )

    with allure.step("Verify hovering actually changes the color"):
        assert footer_hover_color != resting_color, (
            f"The footer link renders {footer_hover_color} whether hovered or "
            "not, so the hover state gives the user no feedback."
        )
