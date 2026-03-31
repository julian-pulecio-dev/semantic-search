from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy.spatial import ConvexHull

Point = Tuple[float, float]  # (x, y) in PDF coordinate space


@dataclass
class PagePolygon:
    """
    Convex hull of the words belonging to a chunk on a single page.

    Coordinates use pdfplumber's top-left origin system (Y increases
    downward). If your PDF renderer uses bottom-left origin (PDF spec),
    flip each point with: y_flipped = page_height - y.
    """

    page_number: int
    points: List[Point]  # convex hull vertices in order


@dataclass
class ChunkBoundingPolygon:
    """
    Resolves the bounding polygon(s) for a chunk of text against the
    word-level coordinates extracted from a PDF.

    Because a chunk can span multiple pages, the result is a list of
    PagePolygon — one per page the chunk touches.

    Matching strategy
    -----------------
    Tokens from the chunk text are normalised (lowercased, punctuation
    stripped) and matched sequentially against the normalised tokens of
    each page's word list. The scan is greedy and stateful across pages,
    so it correctly handles chunks that start mid-page and end mid-page
    on the next one.

    This works well when the chunker preserves the original word order.
    If your chunker reorders or summarises text, a more sophisticated
    matcher (e.g. LCS-based) would be needed.
    """

    # ConvexHull requires at least 3 non-collinear points; below this
    # we fall back to returning the raw corners directly.
    MIN_POINTS_FOR_HULL: int = 3

    def resolve(
        self,
        chunk_text: str,
        pages: List[dict],
    ) -> List[PagePolygon]:
        """
        Resolves the bounding polygons for a chunk across one or more pages.

        Args:
            chunk_text: The raw text of the chunk.
            pages: The list of page dicts returned by PDFTextExtractor.extract(),
                   each containing 'page_number', 'text', and 'words'.
                   Words are dicts with keys: 'text', 'x0', 'x1', 'top', 'bottom'.
        Returns:
            A list of PagePolygon, one per page the chunk touches, in page order.
            Returns an empty list if no matching words are found.
        """
        chunk_tokens = self._tokenize(chunk_text)
        remaining = chunk_tokens  # tokens still to be matched across pages
        polygons = []

        for page in pages:
            if not remaining:
                break

            page_words = page["words"]
            page_tokens = [self._normalize(w["text"]) for w in page_words]

            matched_words, remaining = self._match_tokens(
                remaining, page_tokens, page_words
            )

            if matched_words:
                polygon = self._convex_hull(matched_words)
                if polygon:
                    polygons.append(
                        PagePolygon(
                            page_number=page["page_number"],
                            points=polygon,
                        )
                    )

        return polygons

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        """Splits text into normalised tokens for matching."""
        return [self._normalize(t) for t in text.split()]

    def _normalize(self, token: str) -> str:
        """Lowercases and strips surrounding punctuation for robust matching."""
        return token.lower().strip(".,;:!?\"'()[]{}")

    def _match_tokens(
        self,
        remaining_tokens: List[str],
        page_tokens: List[str],
        page_words: List[dict],
    ) -> Tuple[List[dict], List[str]]:
        """
        Greedily matches as many leading tokens from `remaining_tokens` as
        possible against `page_tokens` using a sequential scan.

        The scan advances through page tokens looking for each next expected
        chunk token. Words that match are collected; the rest are skipped.
        This tolerates minor insertions (e.g. hyphenation artefacts) in the
        extracted text.

        Args:
            remaining_tokens: Normalised chunk tokens not yet matched.
            page_tokens: Normalised tokens for all words on this page.
            page_words: Original word dicts corresponding to page_tokens.
        Returns:
            A tuple of (matched_word_dicts, unmatched_remaining_tokens).
        """
        matched_words = []
        token_idx = 0  # pointer into remaining_tokens

        for i, page_token in enumerate(page_tokens):
            if token_idx >= len(remaining_tokens):
                break
            if page_token == remaining_tokens[token_idx]:
                matched_words.append(page_words[i])
                token_idx += 1

        unmatched = remaining_tokens[token_idx:]
        return matched_words, unmatched

    def _convex_hull(self, words: List[dict]) -> List[Point]:
        """
        Computes the convex hull of the bounding boxes of the given words.

        Each word contributes its four corners as input points, so the hull
        tightly wraps all matched words regardless of their individual sizes.

        Falls back gracefully when:
          - Fewer than MIN_POINTS_FOR_HULL unique points exist → returns raw corners.
          - All points are collinear (ConvexHull raises QhullError) → returns
            an axis-aligned bounding box.

        Args:
            words: Word dicts with 'x0', 'x1', 'top', 'bottom' keys.
        Returns:
            An ordered list of (x, y) vertices forming the convex hull,
            or a degenerate bounding shape for edge cases.
        """
        # Collect all four corners for every matched word.
        points = []
        for w in words:
            points += [
                (w["x0"], w["top"]),
                (w["x1"], w["top"]),
                (w["x0"], w["bottom"]),
                (w["x1"], w["bottom"]),
            ]

        if not points:
            return []

        pts = np.array(points, dtype=float)

        # Deduplicate — collinear/duplicate points cause QhullError.
        pts = np.unique(pts, axis=0)

        if len(pts) < self.MIN_POINTS_FOR_HULL:
            # 1–2 unique points: just return the corners we have.
            return [tuple(p) for p in pts]

        try:
            hull = ConvexHull(pts)
            return [tuple(pts[v]) for v in hull.vertices]
        except Exception:
            # All points are collinear → scipy can't build a 2D hull.
            # Return a tight axis-aligned bounding box instead.
            x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
            x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
