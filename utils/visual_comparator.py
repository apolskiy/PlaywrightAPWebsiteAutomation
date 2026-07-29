"""Pillow-backed pixel comparison used for optional visual regression checks.

The comparator is deliberately threshold-based rather than exact: anti-aliasing
of web fonts differs between browser builds and operating systems, so a strict
byte comparison of two screenshots is guaranteed to be flaky. Callers supply the
per-channel tolerance and the maximum acceptable share of differing pixels.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

#: Per-channel intensity difference below which two pixels are treated as equal.
DEFAULT_CHANNEL_TOLERANCE: int = 12

#: Share of differing pixels tolerated before a comparison is reported as failed.
DEFAULT_MAX_DIFF_RATIO: float = 0.01


@dataclass(frozen=True)
class ComparisonResult:
    """Outcome of comparing a candidate screenshot against its baseline.

    Attributes:
        matched: Whether the candidate stayed within the configured tolerance.
        diff_ratio: Share of pixels that differ beyond the channel tolerance,
            in the range ``0.0`` to ``1.0``.
        diff_png: PNG-encoded amplified difference image, or ``None`` when the
            two images matched and no diff was produced.
    """

    matched: bool
    diff_ratio: float
    diff_png: bytes | None


class VisualComparator:
    """Compares screenshots against stored baselines with a pixel tolerance.

    Args:
        baseline_directory: Directory holding the approved baseline PNG files.
        channel_tolerance: Per-channel intensity delta treated as noise.
        max_diff_ratio: Maximum share of differing pixels that still counts as a
            match.
    """

    def __init__(
        self,
        baseline_directory: Path,
        channel_tolerance: int = DEFAULT_CHANNEL_TOLERANCE,
        max_diff_ratio: float = DEFAULT_MAX_DIFF_RATIO,
    ) -> None:
        self._baseline_directory = baseline_directory
        self._channel_tolerance = channel_tolerance
        self._max_diff_ratio = max_diff_ratio

    def baseline_path(self, baseline_name: str) -> Path:
        """Resolve the on-disk location of one baseline image.

        Args:
            baseline_name: Logical name of the baseline, without extension.

        Returns:
            The full path to the baseline PNG file.
        """
        return self._baseline_directory / f"{baseline_name}.png"

    def has_baseline(self, baseline_name: str) -> bool:
        """Report whether a baseline has been approved already.

        Args:
            baseline_name: Logical name of the baseline, without extension.

        Returns:
            ``True`` when the baseline file exists on disk.
        """
        return self.baseline_path(baseline_name).is_file()

    def save_baseline(self, baseline_name: str, screenshot_png: bytes) -> Path:
        """Persist a screenshot as the approved baseline.

        Args:
            baseline_name: Logical name of the baseline, without extension.
            screenshot_png: PNG-encoded screenshot bytes to store.

        Returns:
            The path the baseline was written to.
        """
        self._baseline_directory.mkdir(parents=True, exist_ok=True)
        target_path = self.baseline_path(baseline_name)
        target_path.write_bytes(screenshot_png)
        return target_path

    def compare(self, baseline_name: str, screenshot_png: bytes) -> ComparisonResult:
        """Compare a screenshot against its stored baseline.

        Args:
            baseline_name: Logical name of the baseline, without extension.
            screenshot_png: PNG-encoded screenshot captured during the test.

        Returns:
            A :class:`ComparisonResult` describing the outcome.

        Raises:
            FileNotFoundError: If no baseline has been approved for that name.
        """
        baseline_file = self.baseline_path(baseline_name)
        if not baseline_file.is_file():
            raise FileNotFoundError(
                f"No approved baseline named '{baseline_name}' in {self._baseline_directory}."
            )

        with Image.open(baseline_file) as baseline_image, Image.open(
            io.BytesIO(screenshot_png)
        ) as candidate_image:
            baseline_rgb = baseline_image.convert("RGB")
            candidate_rgb = candidate_image.convert("RGB")
            # A resized viewport changes the canvas, which is a layout failure in
            # its own right - report it as a total mismatch rather than cropping.
            if baseline_rgb.size != candidate_rgb.size:
                return ComparisonResult(matched=False, diff_ratio=1.0, diff_png=None)
            return self._compare_same_size(baseline_rgb, candidate_rgb)

    def _compare_same_size(
        self, baseline_rgb: Image.Image, candidate_rgb: Image.Image
    ) -> ComparisonResult:
        """Compare two equally sized RGB images.

        Args:
            baseline_rgb: The approved baseline, already converted to RGB.
            candidate_rgb: The captured screenshot, already converted to RGB.

        Returns:
            A :class:`ComparisonResult` describing the outcome.
        """
        difference_image = ImageChops.difference(baseline_rgb, candidate_rgb)
        # Collapse the three channels to the strongest single-channel delta so a
        # pixel counts as changed if any one channel moved beyond the tolerance.
        max_channel_delta = difference_image.convert("L")
        changed_pixel_count = sum(
            pixel_count
            for intensity, pixel_count in enumerate(max_channel_delta.histogram())
            if intensity > self._channel_tolerance
        )
        total_pixel_count = baseline_rgb.width * baseline_rgb.height
        diff_ratio = changed_pixel_count / total_pixel_count if total_pixel_count else 0.0

        if diff_ratio <= self._max_diff_ratio:
            return ComparisonResult(matched=True, diff_ratio=diff_ratio, diff_png=None)
        return ComparisonResult(
            matched=False,
            diff_ratio=diff_ratio,
            diff_png=self._encode_png(ImageChops.invert(max_channel_delta)),
        )

    @staticmethod
    def _encode_png(image: Image.Image) -> bytes:
        """Encode a Pillow image as PNG bytes.

        Args:
            image: The image to encode.

        Returns:
            The PNG-encoded representation, ready to attach to a report.
        """
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
