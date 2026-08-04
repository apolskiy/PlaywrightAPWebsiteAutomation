"""Shared Playwright behavior inherited by every Page Object in the suite.

:class:`BasePage` owns the low-level browser plumbing (navigation, viewport
control, DOM capture) so that concrete Page Objects only describe the semantics
of their own screen. No test module is expected to import this class directly.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page


class BasePage:
    """Common wrapper around a Playwright :class:`~playwright.sync_api.Page`.

    Args:
        page: The Playwright page bound to this Page Object instance.
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    @property
    def page(self) -> Page:
        """The underlying Playwright page.

        Returns:
            The page handed to the constructor. Exposed for fixtures and
            diagnostics hooks; tests should prefer the semantic accessors
            published by the concrete Page Object.
        """
        return self._page

    def open(self, url: str) -> None:
        """Navigate to ``url`` and wait for the initial document to parse.

        ``domcontentloaded`` is deliberate: the site decorates the DOM from a
        ``DOMContentLoaded`` listener, and every subsequent wait in this suite is
        expressed as a web-first assertion rather than a network-idle guess.

        Args:
            url: Absolute URL to navigate to.
        """
        self._page.goto(url, wait_until="domcontentloaded")

    def set_viewport(self, width: int, height: int) -> None:
        """Resize the viewport, triggering any CSS media-query re-layout.

        Args:
            width: Viewport width in CSS pixels.
            height: Viewport height in CSS pixels.
        """
        self._page.set_viewport_size({"width": width, "height": height})

    def title(self) -> str:
        """Return the document title.

        Returns:
            The current value of ``document.title``.
        """
        return self._page.title()

    def dom_snapshot(self) -> str:
        """Capture the fully rendered HTML of the current document.

        Returns:
            The serialized DOM, including any nodes injected by client-side
            scripts. Used by the Claude diagnostics hook on assertion failure.
        """
        return self._page.content()

    def screenshot_png(self) -> bytes:
        """Capture a full-page screenshot.

        Returns:
            PNG-encoded bytes of the entire scrollable page.
        """
        return self._page.screenshot(full_page=True)

    def document_scroll_width(self) -> int:
        """Measure the horizontal scroll extent of the document.

        Returns:
            ``document.documentElement.scrollWidth`` in CSS pixels. A value
            greater than the viewport width means the layout overflows sideways.
        """
        return int(self._page.evaluate("() => document.documentElement.scrollWidth"))

    def viewport_width(self) -> int:
        """Return the current viewport width.

        Returns:
            Width of the viewport in CSS pixels.

        Raises:
            RuntimeError: If the browser context was created without a viewport
                (headless "no viewport" mode), which this suite never does.
        """
        viewport = self._page.viewport_size
        if viewport is None:
            raise RuntimeError("The page was created without a fixed viewport size.")
        return int(viewport["width"])

    @staticmethod
    def computed_color(locator: Locator) -> str:
        """Read the resolved text color of an element.

        Args:
            locator: A locator resolving to exactly one element.

        Returns:
            The computed ``color`` property, always in the browser's normalized
            ``rgb(r, g, b)`` form regardless of how the stylesheet spelled it.
        """
        return str(locator.evaluate("element => getComputedStyle(element).color"))

    @staticmethod
    def image_natural_size(locator: Locator) -> tuple[int, int]:
        """Read an image's intrinsic size once the browser has decoded it.

        Visibility is not proof that an image loaded: an ``<img>`` with alt text
        and explicit dimensions still occupies layout space when its source is
        missing or forbidden. Intrinsic size is the honest signal - a broken
        image reports ``0x0``.

        Args:
            locator: A locator resolving to exactly one ``<img>`` element.

        Returns:
            The ``(naturalWidth, naturalHeight)`` pair in pixels, or ``(0, 0)``
            when the image failed to load.
        """
        width, height = locator.evaluate(
            "async image => {"
            "  try { await image.decode(); } catch (error) { /* broken source */ }"
            "  return [image.naturalWidth, image.naturalHeight];"
            "}"
        )
        return int(width), int(height)

    def published_suite_counts(self) -> dict[str, int]:
        """Read every suite-size figure the current page publishes to a reader.

        The site quotes the size of this suite in prose, on more than one page.
        Those figures are marked up rather than left as bare text so a test can
        read exactly what a reader sees, which is what allows the claim to be
        compared against the suite instead of maintained by hand.

        Returns:
            Mapping of scope name - ``total`` for the whole suite, ``deploy``
            for the deployment path - to the integer the page displays. Scopes
            the page does not mention are absent rather than zero.
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
        """Detect whether the layout scrolls sideways at the current viewport.

        Returns:
            ``True`` when the document is wider than the viewport. Sub-pixel
            rounding is tolerated by allowing a one-pixel margin.
        """
        return self.document_scroll_width() > self.viewport_width() + 1

    @staticmethod
    def distinct_row_count(locator: Locator) -> int:
        """Count how many distinct horizontal rows a locator's elements occupy.

        Bounding boxes are only read after every matched element has been laid
        out, so the measurement reflects a settled layout rather than a frame
        captured mid-reflow.

        Args:
            locator: A locator resolving to one or more visible elements.

        Returns:
            The number of unique vertical offsets among the matched elements.
            ``1`` means a single row; anything greater means the elements
            wrapped onto additional lines.
        """
        vertical_offsets: set[int] = set()
        for element_index in range(locator.count()):
            bounding_box = locator.nth(element_index).bounding_box()
            if bounding_box is not None:
                # Round to whole pixels: sub-pixel layout rounding differs per
                # platform and would otherwise report false extra rows.
                vertical_offsets.add(round(bounding_box["y"]))
        return len(vertical_offsets)
