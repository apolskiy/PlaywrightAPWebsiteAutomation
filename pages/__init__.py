"""The Page Object package, which holds all of the suite's DOM knowledge.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains no logic. It re-exports ``BasePage``, ``LandingPage``,
``NavigationTab`` and ``RoutePage`` so callers import them from ``pages``.

Fixtures in ``conftest.py`` build these objects and every test module drives
the site through them; test modules hold no raw selectors. An import error here
stops collection before any test runs.

Specified by ``README.md`` section "Project Architecture".
"""

from pages.base_page import BasePage
from pages.landing_page import LandingPage, NavigationTab
from pages.route_page import RoutePage

__all__ = ["BasePage", "LandingPage", "NavigationTab", "RoutePage"]
