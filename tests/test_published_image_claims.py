"""Tests that the published container image holds what the HTTP Emulators tab claims.

Created: 2026-08-03
Last updated: 2026-11-10

This file covers one behavior: the ``apolskiy/flask_app`` image installs exactly
Flask and its six transitive dependencies, with base packaging tooling
subtracted. It reads the image through ``utils.registry_client`` and compares
the installed distributions against ``EXPECTED_DISTRIBUTIONS``.

The case is marked ``external`` and runs weekly, off the deployment path,
because it reads Docker Hub. A failure means the published image no longer
matches the page: a distribution outside the set means a development dependency
reached a public image, a missing one means the image no longer runs what the
tab advertises, and an empty read means the image or its manifest could not be
read at all.

**It checks contents, not behavior.** Nothing about a careless rebuild shows in
the browser: the tab renders, the link resolves, and only reading the image
catches the claim going false. Whether the image serves requests is tested in
the image's own repository.

Specified by ``README.md`` section "Key Features" (Published Artefact
Verification, Off the Deploy Path).
"""

from __future__ import annotations

import allure
import pytest

from utils.registry_client import BASE_IMAGE_DISTRIBUTIONS, application_distributions

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Published Artefact Integrity"

#: THE ADVERTISED IMAGE, as the HTTP Emulators tab names it to readers.
PUBLISHED_IMAGE: str = "apolskiy/flask_app"

#: THE CLAIMED CLOSURE. Flask plus exactly its transitive dependencies, the set
#: the site claims. A name outside it, or missing from it, fails the case.
EXPECTED_DISTRIBUTIONS: frozenset[str] = frozenset(
    {"flask", "blinker", "click", "itsdangerous", "jinja2", "markupsafe", "werkzeug"}
)


@pytest.mark.test_id("PAWA_10032")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The published image installs only the dependencies the site claims")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.external
def test_published_image_carries_only_the_declared_dependency_closure() -> None:
    """Assert the published image installs Flask's closure and nothing besides.

    The read must return at least one distribution beyond base tooling, none
    outside ``EXPECTED_DISTRIBUTIONS``, and every name in it.

    Returns:
        None
    """
    with allure.step(f"Read the distributions installed in {PUBLISHED_IMAGE}"):
        installed = application_distributions(PUBLISHED_IMAGE)
        allure.attach(
            "\n".join(f"{name}=={version}" for name, version in sorted(installed.items())),
            name=f"Distributions installed in {PUBLISHED_IMAGE}",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify the image was readable and is not empty"):
        assert installed, (
            f"{PUBLISHED_IMAGE} reported no installed distributions beyond base "
            f"tooling ({', '.join(sorted(BASE_IMAGE_DISTRIBUTIONS))}). Either the "
            "image no longer installs its requirements or the registry returned a "
            "manifest this check cannot read."
        )

    with allure.step("Verify nothing beyond the declared closure reached the image"):
        unexpected = sorted(set(installed) - EXPECTED_DISTRIBUTIONS)
        assert not unexpected, (
            f"{PUBLISHED_IMAGE} ships distributions the site does not claim: "
            f"{unexpected}. The tab advertises a Flask-only image, so a test or "
            "lint dependency reaching it makes the published claim false."
        )

    with allure.step("Verify the image still installs everything the closure needs"):
        missing = sorted(EXPECTED_DISTRIBUTIONS - set(installed))
        assert not missing, (
            f"{PUBLISHED_IMAGE} is missing {missing}. The image cannot serve the "
            "error catalogue the tab describes without its full Flask closure."
        )
