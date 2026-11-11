"""Tests that figures a project panel quotes from another repository match their source.

Created: 2026-11-10
Last updated: 2026-11-10

This file covers one behavior: every figure the Multi-LLM Evaluation tab marks
as copied from another repository's README (test cases, requirements traced,
recorded responses) equals the value the Status table of that README states.
It reads the marked figures through ``LandingPage.published_project_figures``
and each README through ``utils.readme_figures``.

The case is marked ``external`` and runs weekly, off the deployment path,
because it reads ``raw.githubusercontent.com``. A failure means the page quotes
a figure its source has revised, quotes one its source no longer states, marks
a figure no pattern can locate, or marks no figures at all.

**A copied number is true only on the day it is copied.** The source project
moves on while the tab keeps rendering, so each figure is marked up with the
repository and figure name it came from and read back against its source. A
figure the README no longer states fails too, since the page would then quote
a number with no source. A README drifts over weeks, not between pushes, which
is why weekly is often enough and GitHub being briefly unreachable must not
fail a deploy.

Specified by ``README.md`` section "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest

from pages.landing_page import LandingPage
from utils.readme_figures import FIGURE_PATTERNS, fetch_readme, readme_url, stated_figure

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Published Figures Match Their Source"


@pytest.mark.test_id("PAWA_10043")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Figures quoted from another repository match that repository's README")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.external
def test_project_figures_match_their_source_readme(desktop_page: LandingPage) -> None:
    """Assert every marked figure equals the value its source README states.

    The page must mark at least one figure, every marked figure must have a
    pattern in ``FIGURE_PATTERNS``, each must still be stated by its README,
    and each stated value must equal the one on the page.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Read every figure the page attributes to another repository"):
        published = landing_page.published_project_figures()
        allure.attach(
            "\n".join(f"{repo} {figure} = {value}" for repo, figure, value in published),
            name="Figures published on the page",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify the page publishes marked figures at all"):
        assert published, (
            "The page marks no figure as copied from another repository, so there "
            "is nothing to verify. If the figures were removed, remove this test; "
            "if they lost their markup, they are now unverified claims."
        )

    with allure.step("Verify every marked figure has a known source pattern"):
        unknown = sorted(
            {entry[:2] for entry in published} - set(FIGURE_PATTERNS)
        )
        assert not unknown, (
            f"The page marks figures {unknown} that no pattern in "
            "utils/readme_figures.py knows how to find, so nothing can verify them."
        )

    readmes: dict[str, str] = {}
    for repository in sorted({entry[0] for entry in published}):
        with allure.step(f"Read the README of {repository}"):
            readmes[repository] = fetch_readme(repository)

    unstated: list[str] = []
    mismatched: list[str] = []
    with allure.step("Compare each figure against the value its README states"):
        for repository, figure, value in published:
            stated = stated_figure(readmes[repository], repository, figure)
            if stated is None:
                unstated.append(f"{repository} {figure} ({readme_url(repository)})")
            elif stated != value:
                mismatched.append(
                    f"{repository} {figure}: the page says {value}, the README says {stated}"
                )

    with allure.step("Verify every figure is still stated by its source"):
        assert not unstated, (
            f"These READMEs no longer state a figure the page quotes: {unstated}. "
            "Either the README was reworded, and the pattern needs updating, or the "
            "figure was dropped, and the page is quoting a number with no source."
        )

    with allure.step("Verify every figure matches its source"):
        assert not mismatched, (
            "The page quotes figures its source has since revised: "
            f"{mismatched}. Update the Multi-LLM Evaluation tab."
        )
