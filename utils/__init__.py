"""The utilities package: AI failure triage, site discovery and visual diffing.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains no logic. It re-exports ``ClaudeTestInspector`` and
``FailureContext`` from ``utils.claude_inspector``; ``SiteMapCrawler``,
``DiscoveredRoute``, ``JavaScriptError``, ``discover_routes`` and
``load_sitemap`` from ``utils.site_crawler``; and ``VisualComparator`` and
``ComparisonResult`` from ``utils.visual_comparator``. The other utility
modules are imported by their full path.

``conftest.py`` and the dynamic route suite import from here. An import error
here stops collection before any test runs.

Specified by ``README.md`` section "Project Architecture".
"""

from utils.claude_inspector import ClaudeTestInspector, FailureContext
from utils.site_crawler import (
    DiscoveredRoute,
    JavaScriptError,
    SiteMapCrawler,
    discover_routes,
    load_sitemap,
)
from utils.visual_comparator import ComparisonResult, VisualComparator

__all__ = [
    "ClaudeTestInspector",
    "ComparisonResult",
    "DiscoveredRoute",
    "FailureContext",
    "JavaScriptError",
    "SiteMapCrawler",
    "VisualComparator",
    "discover_routes",
    "load_sitemap",
]
