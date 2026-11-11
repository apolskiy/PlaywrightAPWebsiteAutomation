"""Browser plumbing every Page Object in the suite inherits.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``BasePage``, which navigates, resizes the viewport, waits
for sub-resources, captures the title, DOM and a screenshot, measures layout
(scroll width, overflow, wrapped rows, an image's intrinsic size, a computed
color) and reads the suite-size figures a page publishes. It also contains the
``SUB_RESOURCE_SETTLE_TIMEOUT_MS`` bound.

``LandingPage`` and ``RoutePage`` extend it, and no test module imports it
directly. The fixtures in ``conftest.py`` construct those subclasses, and the
failure hook reads the DOM, screenshot and diagnostics through this class, so a
fault here shows up in every suite and in every failure report at once.

**Every page carries a diagnostics recorder.** ``self.diagnostics`` is a
``PageDiagnostics`` collaborator rather than more methods on this class, because
it drives nothing and reads nothing; it only listens. Fixtures arm it before the
first navigation, since Playwright delivers no event that predates its listener.

**Navigation waits for ``domcontentloaded`` only.** The site decorates its DOM
from a ``DOMContentLoaded`` listener, and every later wait is a web-first
assertion rather than a network-idle guess.

**Settling sub-resources is short and never fatal.** ``settle_sub_resources``
waits for ``load`` so a broken stylesheet or icon has reported itself before a
check reads the error log. A timeout returns False rather than failing, because
the page embeds CI badges served by GitHub and a slow ``load`` must not bring a
third party's availability into the verdict.

**An image is loaded when it has an intrinsic size.** Visibility proves nothing:
an ``<img>`` with alt text and explicit dimensions occupies layout space when its
source is missing, while a broken image reports ``0x0``.

**Row counts round to whole pixels**, since sub-pixel layout rounding differs
per platform and would otherwise report extra rows.

Specified by ``README.md`` sections "Test Design Principles" and "Project
Architecture", and the Key Features entries "Origin-Scoped Assertions" and
"Published Figures Verify Themselves".
"""

from __future__ import annotations

from typing import Final

from playwright.sync_api import Error as PlaywrightError, Locator, Page

from utils.page_diagnostics import PageDiagnostics

#: BOUNDED AND NOT FATAL (added 2026-08-11). How long, in milliseconds,
#: :meth:`BasePage.settle_sub_resources` lets sub-resources finish before the
#: diagnostic log is read.
SUB_RESOURCE_SETTLE_TIMEOUT_MS: Final[int] = 5_000


class BasePage:
    """Wrap a Playwright :class:`~playwright.sync_api.Page` with shared behavior.

    Args:
        page (Page): The Playwright page bound to this Page Object.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        #: Records the errors the browser raises against this page (added
        #: 2026-08-11). Fixtures arm it before the first navigation.
        self.diagnostics = PageDiagnostics(page)

    @property
    def page(self) -> Page:
        """Return the underlying Playwright page.

        Returns:
            Page: The page handed to the constructor, for fixtures and
            diagnostics hooks. Tests use the concrete Page Object's semantic
            accessors instead.
        """
        return self._page

    def open(self, url: str) -> None:
        """Navigate to ``url`` and wait for the initial document to parse.

        Args:
            url (str): The absolute URL to navigate to.

        Returns:
            None
        """
        self._page.goto(url, wait_until="domcontentloaded")

    def set_viewport(self, width: int, height: int) -> None:
        """Resize the viewport, triggering any CSS media-query re-layout.

        Args:
            width (int): The viewport width in CSS pixels.
            height (int): The viewport height in CSS pixels.

        Returns:
            None
        """
        self._page.set_viewport_size({"width": width, "height": height})

    def settle_sub_resources(self) -> bool:
        """Wait briefly for images, styles and scripts to finish loading.

        Waits up to ``SUB_RESOURCE_SETTLE_TIMEOUT_MS`` for the ``load`` event. A
        caller that did not settle reports on whatever had been observed by then.

        Returns:
            bool: True when ``load`` arrived within the timeout, False when the
            wait expired or the page could not be reached.
        """
        try:
            self._page.wait_for_load_state(
                "load", timeout=SUB_RESOURCE_SETTLE_TIMEOUT_MS
            )
            return True
        except PlaywrightError:
            return False

    def title(self) -> str:
        """Return the document title.

        Returns:
            str: The current value of ``document.title``.
        """
        return self._page.title()

    def dom_snapshot(self) -> str:
        """Return the fully rendered HTML of the current document.

        Returns:
            str: The serialized DOM, including nodes injected by client-side
            scripts. The Claude diagnostics hook reads it on failure.
        """
        return self._page.content()

    def screenshot_png(self) -> bytes:
        """Return a full-page screenshot.

        Returns:
            bytes: PNG-encoded bytes of the entire scrollable page.
        """
        return self._page.screenshot(full_page=True)

    def document_scroll_width(self) -> int:
        """Return the horizontal scroll extent of the document.

        Returns:
            int: ``document.documentElement.scrollWidth`` in CSS pixels. A value
            greater than the viewport width means the layout overflows sideways.
        """
        return int(self._page.evaluate("() => document.documentElement.scrollWidth"))

    def viewport_width(self) -> int:
        """Return the current viewport width.

        Returns:
            int: The width of the viewport in CSS pixels.

        Raises:
            RuntimeError: When the browser context was created without a
                viewport ("no viewport" mode), which this suite never does.
        """
        viewport = self._page.viewport_size
        if viewport is None:
            raise RuntimeError("The page was created without a fixed viewport size.")
        return int(viewport["width"])

    @staticmethod
    def computed_color(locator: Locator) -> str:
        """Return the resolved text color of an element.

        Args:
            locator (Locator): A locator resolving to exactly one element.

        Returns:
            str: The computed ``color`` property, always in the browser's
            normalized ``rgb(r, g, b)`` form however the stylesheet spelled it.
        """
        return str(locator.evaluate("element => getComputedStyle(element).color"))

    @staticmethod
    def image_natural_size(locator: Locator) -> tuple[int, int]:
        """Return an image's intrinsic size once the browser has decoded it.

        Args:
            locator (Locator): A locator resolving to exactly one ``<img>``.

        Returns:
            tuple[int, int]: The ``(naturalWidth, naturalHeight)`` pair in
            pixels, or ``(0, 0)`` when the image failed to load.
        """
        width, height = locator.evaluate(
            "async image => {"
            "  try { await image.decode(); } catch (error) { /* broken source */ }"
            "  return [image.naturalWidth, image.naturalHeight];"
            "}"
        )
        return int(width), int(height)

    def published_suite_counts(self) -> dict[str, int]:
        """Return every suite-size figure the current page shows a reader.

        Reads each ``span.suite-count`` element by its ``data-scope``.

        Returns:
            dict[str, int]: The displayed integer per scope, ``total`` for the
            whole suite and ``deploy`` for the deployment path. A scope the page
            does not mention is absent rather than zero.
        """
        return {
            str(scope): int(text.strip())
            for scope, text in self._page.eval_on_selector_all(
                "span.suite-count",
                "nodes => nodes.map(node => [node.dataset.scope, node.textContent])",
            )
            if scope and text.strip().isdigit()
        }

    def has_horizontal_overflow(self) -> bool:
        """Return whether the layout scrolls sideways at the current viewport.

        Returns:
            bool: True when the document is wider than the viewport by more than
            one pixel, the margin allowed for sub-pixel rounding.
        """
        return self.document_scroll_width() > self.viewport_width() + 1

    @staticmethod
    def distinct_row_count(locator: Locator) -> int:
        """Return how many distinct horizontal rows a locator's elements occupy.

        Bounding boxes are read only after every matched element is laid out, so
        the count reflects a settled layout rather than a mid-reflow frame.

        Args:
            locator (Locator): A locator resolving to one or more visible
                elements.

        Returns:
            int: The number of unique vertical offsets among the elements.
            ``1`` means a single row; more means they wrapped.
        """
        vertical_offsets: set[int] = set()
        for element_index in range(locator.count()):
            bounding_box = locator.nth(element_index).bounding_box()
            if bounding_box is not None:
                # Decided 2026-07-28: round to whole pixels, since sub-pixel
                # rounding differs per platform and reports false extra rows.
                vertical_offsets.add(round(bounding_box["y"]))
        return len(vertical_offsets)
