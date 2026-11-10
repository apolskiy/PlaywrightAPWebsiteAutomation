"""Coverage for the figures a project panel copies from another repository.

The Multi-LLM Evaluation tab quotes how large that project is - test cases,
requirements traced, recorded responses - and every one of those numbers
belongs to a repository this site does not control. They were copied from the
Status tables of the two READMEs, and a copied number is true only on the day
it is copied: the project moves on, the tab keeps rendering, and the page goes
on advertising a figure its own source has since revised.

So the figures are marked up with the repository and the name of the figure
they came from, and this test reads each one back off the page and compares it
against the README that states it. A figure the README no longer states at all
fails too, because the site would then be quoting a number with no source.

Marked ``external``: it reads raw.githubusercontent.com, so it is deselected on
the deployment path and runs weekly with the other checks that depend on a
third party. A README drifts over weeks, not between pushes, and GitHub being
briefly unreachable is no reason to fail a deploy.
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
    """Every marked figure must equal the value its source README states.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
