"""Tests that the suite-size figures the site quotes match the suite that is running.

Created: 2026-08-03
Last updated: 2026-11-10

This file covers two behaviors: the Web Automation tab and the CI case study
each quote the collected total and the deployment-path count of this suite. The
private ``_assert_matches`` helper holds the three assertions both cases share,
and ``CASE_STUDY_ROUTE`` names the second page.

The cases run on the deployment path and read their expected figures from the
``suite_size`` fixture, which ``conftest.py`` measures during collection. A
failure means a page advertises a suite size the suite no longer has, or
carries no marked figure to verify; the fix is to the page, not to this file.

**Counts come from collection, not from the current selection**, so running a
subset never makes the figure look wrong. A run that names specific files or
selects more than one browser engine measures something the figure never
described, and both cases skip with the fixture's reason instead of asserting.

Specified by ``README.md`` sections "Key Features" (Published Figures Verify
Themselves) and "Quick Start".
"""

from __future__ import annotations

import allure
import pytest

from conftest import SuiteSize
from config.settings import Settings
from pages.landing_page import LandingPage
from pages.route_page import RoutePage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Published Suite Size"

#: SECOND QUOTING PAGE. The case study's route, which quotes the same figures
#: as the landing page.
CASE_STUDY_ROUTE = "case-study.html"


def _assert_matches(published: dict[str, int], suite_size: SuiteSize, page_name: str) -> None:
    """Assert the figures a page publishes match the collected suite.

    The page must publish at least one marked figure, its ``total`` must equal
    the collected total, and its ``deploy`` must equal the count not marked
    ``external``.

    Args:
        published (dict[str, int]): The scope-to-number mapping read from the page.
        suite_size (SuiteSize): The suite size measured during collection.
        page_name (str): The page's name as failure messages show it.

    Returns:
        None
    """
    with allure.step(f"Verify {page_name} publishes a suite size at all"):
        assert published, (
            f"{page_name} publishes no marked suite-size figure. The numbers are "
            "read back from the markup to keep them honest, so an unmarked figure "
            "is one nothing can verify."
        )

    with allure.step(f"Verify {page_name} quotes the collected total"):
        assert published.get("total") == suite_size.total, (
            f"{page_name} advertises {published.get('total')} tests but the suite "
            f"collects {suite_size.total}. Update the published figure, or the page "
            "is telling a reader something that is no longer true."
        )

    with allure.step(f"Verify {page_name} quotes the deployment-path count"):
        assert published.get("deploy") == suite_size.deployment, (
            f"{page_name} advertises {published.get('deploy')} tests on the "
            f"deployment path but {suite_size.deployment} are not marked external. "
            "Marking a test external changes what a deploy actually gates on."
        )


@pytest.mark.test_id("PAWA_10033")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The landing page quotes the suite size it actually has")
@allure.severity(allure.severity_level.NORMAL)
def test_landing_page_publishes_the_actual_suite_size(
    desktop_page: LandingPage, suite_size: SuiteSize
) -> None:
    """Assert the Web Automation tab quotes the collected suite size.

    Skips when the run is not comparable with the published figure.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        suite_size (SuiteSize): The suite size measured during collection.

    Returns:
        None
    """
    if suite_size.incomparable_reason is not None:
        pytest.skip(suite_size.incomparable_reason)

    landing_page = desktop_page.navigate()

    with allure.step("Read the suite-size figures published on the landing page"):
        published = landing_page.published_suite_counts()

    _assert_matches(published, suite_size, "The Web Automation tab")


@pytest.mark.test_id("PAWA_10034")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The case study quotes the suite size it actually has")
@allure.severity(allure.severity_level.NORMAL)
def test_case_study_publishes_the_actual_suite_size(
    desktop_route_page: RoutePage,
    framework_settings: Settings,
    suite_size: SuiteSize,
) -> None:
    """Assert the case study's cost table quotes the collected suite size.

    Skips when the run is not comparable with the published figure.

    Args:
        desktop_route_page (RoutePage): The route Page Object at 1920x1080.
        framework_settings (Settings): The resolved framework configuration.
        suite_size (SuiteSize): The suite size measured during collection.

    Returns:
        None
    """
    if suite_size.incomparable_reason is not None:
        pytest.skip(suite_size.incomparable_reason)

    with allure.step(f"Open /{CASE_STUDY_ROUTE}"):
        desktop_route_page.open(framework_settings.resolve_url(CASE_STUDY_ROUTE))

    with allure.step("Read the suite-size figures published in the case study"):
        published = desktop_route_page.published_suite_counts()

    _assert_matches(published, suite_size, "The CI case study")
