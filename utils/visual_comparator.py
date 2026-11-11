"""Compares screenshots against stored baselines within a pixel tolerance.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``VisualComparator``, which stores approved baseline PNGs,
compares a screenshot against one and encodes a difference image, and
``ComparisonResult``, the outcome it returns: whether the images matched, the
share of pixels that differ and, on a mismatch, the difference image.

No test uses it yet. It is exported by ``utils`` for a visual regression check
to call with a screenshot from a Page Object; a mismatch would then be that
check's failure, with the difference image as its evidence.

**Threshold-based, not exact.** Web font anti-aliasing differs between browser
builds and operating systems, so a byte comparison of two screenshots would be
flaky. A pixel counts as changed when the grayscale luminance of its RGB
difference exceeds the channel tolerance, and the comparison matches while the
share of changed pixels stays at or below the allowed ratio.

**A size change is a total mismatch.** A resized canvas is a layout failure in
its own right, so it is reported as a ratio of ``1.0`` rather than cropped.

Specified by ``README.md`` section "Project Architecture".
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

#: NOISE FLOOR. The difference intensity at or below which a pixel is unchanged.
DEFAULT_CHANNEL_TOLERANCE: int = 12

#: TOLERATED SHARE of changed pixels before a comparison fails.
DEFAULT_MAX_DIFF_RATIO: float = 0.01


@dataclass(frozen=True)
class ComparisonResult:
    """Hold the outcome of comparing a screenshot against its baseline.

    Attributes:
        matched (bool): Whether the screenshot stayed within the tolerance.
        diff_ratio (float): The share of pixels changed beyond the tolerance,
            from ``0.0`` to ``1.0``.
        diff_png (bytes | None): A PNG of the inverted difference image, or None
            when the images matched or differed in size.
    """

    matched: bool
    diff_ratio: float
    diff_png: bytes | None


class VisualComparator:
    """Compare screenshots against stored baselines with a pixel tolerance.

    Args:
        baseline_directory (Path): The directory holding approved baseline PNGs.
        channel_tolerance (int): The difference intensity treated as noise.
        max_diff_ratio (float): The largest share of changed pixels that still
            counts as a match.
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
        """Return the on-disk location of one baseline image.

        Args:
            baseline_name (str): The baseline's name, without extension.

        Returns:
            Path: The full path to the baseline PNG.
        """
        return self._baseline_directory / f"{baseline_name}.png"

    def has_baseline(self, baseline_name: str) -> bool:
        """Return whether a baseline has been approved already.

        Args:
            baseline_name (str): The baseline's name, without extension.

        Returns:
            bool: True when the baseline file exists on disk.
        """
        return self.baseline_path(baseline_name).is_file()

    def save_baseline(self, baseline_name: str, screenshot_png: bytes) -> Path:
        """Write a screenshot as the approved baseline.

        Args:
            baseline_name (str): The baseline's name, without extension.
            screenshot_png (bytes): The PNG-encoded screenshot to store.

        Returns:
            Path: The path the baseline was written to.
        """
        self._baseline_directory.mkdir(parents=True, exist_ok=True)
        target_path = self.baseline_path(baseline_name)
        target_path.write_bytes(screenshot_png)
        return target_path

    def compare(self, baseline_name: str, screenshot_png: bytes) -> ComparisonResult:
        """Return the result of comparing a screenshot against its baseline.

        Args:
            baseline_name (str): The baseline's name, without extension.
            screenshot_png (bytes): The PNG-encoded screenshot from the test.

        Returns:
            ComparisonResult: The outcome; a size difference is a mismatch with
            a ratio of ``1.0`` and no difference image.

        Raises:
            FileNotFoundError: When no baseline has been approved for the name.
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
            # Decided 2026-07-28: a resized canvas is a layout failure in its own
            # right, reported as a total mismatch rather than cropped.
            if baseline_rgb.size != candidate_rgb.size:
                return ComparisonResult(matched=False, diff_ratio=1.0, diff_png=None)
            return self._compare_same_size(baseline_rgb, candidate_rgb)

    def _compare_same_size(
        self, baseline_rgb: Image.Image, candidate_rgb: Image.Image
    ) -> ComparisonResult:
        """Return the result of comparing two equally sized RGB images.

        Args:
            baseline_rgb (Image.Image): The approved baseline, in RGB.
            candidate_rgb (Image.Image): The captured screenshot, in RGB.

        Returns:
            ComparisonResult: The outcome, with an inverted difference image on
            a mismatch.
        """
        difference_image = ImageChops.difference(baseline_rgb, candidate_rgb)
        # Collapse the three channels to one grayscale luminance value per pixel;
        # a pixel counts as changed when that value exceeds the tolerance.
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
        """Return a Pillow image encoded as PNG bytes.

        Args:
            image (Image.Image): The image to encode.

        Returns:
            bytes: The PNG encoding, ready to attach to a report.
        """
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
