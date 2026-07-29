"""Supporting utilities: AI failure triage, site discovery, and visual diffing."""

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
