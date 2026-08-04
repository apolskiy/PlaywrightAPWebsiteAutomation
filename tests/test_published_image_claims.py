"""Coverage for the container claim published on the HTTP Emulators tab.

The site states that the ``apolskiy/flask_app`` image carries Flask and its six
transitive dependencies and nothing else. Every other assertion in this suite
checks that the page says what it means to say; this one checks that what it
says is still true of the artefact a reader would pull.

The failure this guards against is silent. Nothing about a careless rebuild
looks wrong from the browser: the tab keeps rendering, the link keeps
resolving, and the published size claim simply stops matching the image behind
it. Only reading the image catches that.

Marked ``external``: it resolves a third party, so it is deselected on the
deployment path for the same reason the link-rot check is. A dependency
regression in a container is a monthly risk, not a per-push one, and Docker Hub
does not belong in the critical path of a deploy signal.
"""

from __future__ import annotations

import allure
import pytest

from utils.registry_client import BASE_IMAGE_DISTRIBUTIONS, application_distributions

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Published Artefact Integrity"

#: The image the HTTP Emulators tab advertises to readers.
PUBLISHED_IMAGE: str = "apolskiy/flask_app"

#: Flask plus exactly its transitive closure - the set the site claims. Anything
#: outside it means a development dependency reached a public image; anything
#: missing from it means the image no longer runs what it advertises.
EXPECTED_DISTRIBUTIONS: frozenset[str] = frozenset(
    {"flask", "blinker", "click", "itsdangerous", "jinja2", "markupsafe", "werkzeug"}
)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The published image installs only the dependencies the site claims")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.external
def test_published_image_carries_only_the_declared_dependency_closure() -> None:
    """The published image must install Flask's closure and nothing besides."""
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
