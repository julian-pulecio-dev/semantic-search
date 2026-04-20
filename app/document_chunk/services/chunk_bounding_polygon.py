from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    coverage: float = 1.0  # fraction of chunk tokens that matched


@dataclass
class ChunkBoundingPolygon:
    """
    Resolves the bounding polygon(s) for a chunk of text against the
    word-level coordinates extracted from a PDF.

    Because a chunk can span multiple pages, the result is a list of
    PagePolygon — one per page the chunk touches.

    Matching strategy
    -----------------
    Phase 1 — Overlap-aware anchor:
        Chunk splitters commonly repeat the last N tokens of chunk K at
        the start of chunk K+1 (overlap). Those tokens were already
        consumed by the cursor, so anchoring on them would find a
        position *after* where the real chunk content begins — causing
        the polygon to swallow all the intermediate words between the
        overlap region and the first new word.

        To avoid this, the anchor is taken from tokens starting at
        `overlap_skip` (set to the splitter's overlap token budget).
        This positions the anchor at the first genuinely new content.

        The anchor tokens must appear (nearly) contiguously on the page
        — a gap of at most 1 page-word is allowed to absorb minor PDF
        extraction artefacts such as hyphenation markers.

        If no anchor is found the chunk is not on this page.

    Phase 2 — Backward fill:
        Once anchored, scan backward from the anchor start to collect
        the overlap tokens that precede the anchor. This ensures the
        polygon covers the full chunk text including the repeated
        prefix, while still anchoring on unambiguous new content.

    Phase 3 — Forward extension with bounded gap:
        Advance token-by-token through the remaining chunk tokens. At
        most `max_gap` page-words may be skipped between consecutive
        chunk tokens, tolerating artefacts without unbounded drift.

    Phase 4 — Coverage gate:
        If fewer than `min_coverage` × len(chunk_tokens) tokens match,
        the page polygon is discarded.
    """

    MIN_POINTS_FOR_HULL: int = 3

    # Number of tokens to skip at the start of the chunk when searching
    # for the anchor. Set this to the approximate token count of the
    # splitter's overlap so the anchor lands on genuinely new content.
    # A rough estimate (e.g. 40-60 for chunk_overlap=50 with cl100k_base)
    # is fine; exact precision is not required.
    overlap_skip: int = 0

    # Number of anchor tokens (after the overlap region) that must appear
    # contiguously to confirm the chunk's position on the page.
    anchor_size: int = 5

    # Maximum number of page-words that may be skipped between two
    # consecutive chunk tokens during forward extension.
    max_gap: int = 4

    # Minimum fraction of chunk tokens that must match for a page
    # polygon to be emitted.
    min_coverage: float = 0.6

    def resolve(
        self,
        chunk_text: str,
        pages: List[dict],
        page_cursors: Optional[Dict[int, int]] = None,
    ) -> Tuple[List[PagePolygon], Dict[int, int]]:
        """
        Resolves the bounding polygons for a chunk across one or more pages.

        Args:
            chunk_text: The raw text of the chunk.
            pages: List of page dicts from PDFTextExtractor.extract(), each
                   with 'page_number', 'text', and 'words'. Words are dicts
                   with keys 'text', 'x0', 'x1', 'top', 'bottom'.
            page_cursors: Maps page_number to the first unconsumed word index
                          on that page. Ensures chunk N never re-matches words
                          already claimed by chunk N-1. Pass None to start
                          from word 0 on every page.
        Returns:
            (polygons, updated_cursors) where polygons is one PagePolygon per
            page the chunk touches (in page order), and updated_cursors is the
            advanced cursor state to pass into the next call.
        """
        if page_cursors is None:
            page_cursors = {}

        chunk_tokens = self._tokenize(chunk_text)
        if not chunk_tokens:
            return [], dict(page_cursors)

        remaining = chunk_tokens
        polygons: List[PagePolygon] = []
        updated_cursors = dict(page_cursors)

        for page in pages:
            if not remaining:
                break

            page_num = page["page_number"]
            page_words = page["words"]
            page_tokens = [self._normalize(w["text"]) for w in page_words]
            start_from = page_cursors.get(page_num, 0)

            matched_words, remaining, next_cursor, coverage = (
                self._match_tokens(
                    remaining, page_tokens, page_words, start_from
                )
            )

            if matched_words and coverage >= self.min_coverage:
                updated_cursors[page_num] = next_cursor
                polygon = self._convex_hull(matched_words)
                if polygon:
                    polygons.append(
                        PagePolygon(
                            page_number=page_num,
                            points=polygon,
                            coverage=coverage,
                        )
                    )

        return polygons, updated_cursors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_tokens(
        self,
        remaining_tokens: List[str],
        page_tokens: List[str],
        page_words: List[dict],
        start_from: int = 0,
    ) -> Tuple[List[dict], List[str], int, float]:
        """
        Overlap-aware four-phase matching.

        Returns:
            (matched_word_dicts, unmatched_remaining_tokens,
             next_cursor, coverage)
        """
        n = len(remaining_tokens)

        # ── Phase 1: anchor past the overlap region ───────────────────
        # Skip `overlap_skip` tokens to land on the first genuinely new
        # content. Clamp so we always have at least `anchor_size` tokens
        # available; very short chunks anchor on their first tokens.
        anchor_offset = min(self.overlap_skip, max(0, n - self.anchor_size))
        effective_anchor_size = min(self.anchor_size, n - anchor_offset)

        anchor_tokens = remaining_tokens[
            anchor_offset: anchor_offset + effective_anchor_size
        ]

        anchor_start_page, anchor_end_page = self._find_anchor(
            anchor_tokens, page_tokens, 0
        )

        if anchor_start_page is None:
            # New content of this chunk is not on this page.
            return [], remaining_tokens, start_from, 0.0

        # ── Phase 2: backward fill — collect the overlap prefix ───────
        # Walk backward from the anchor start to pick up tokens that
        # belong to the chunk's overlap prefix (already-seen text that
        # opens the chunk). We match in reverse and stop on the first
        # miss so we don't accidentally absorb unrelated preceding words.
        prefix_words: List[dict] = []
        page_back = anchor_start_page - 1
        for tok in reversed(remaining_tokens[:anchor_offset]):
            found = False
            for back in range(
                page_back,
                max(start_from - 1, page_back - self.max_gap - 1),
                -1,
            ):
                if back >= 0 and page_tokens[back] == tok:
                    prefix_words.insert(0, page_words[back])
                    page_back = back - 1
                    found = True
                    break
            if not found:
                break

        # ── Assemble initial matched set ──────────────────────────────
        matched_words: List[dict] = prefix_words + list(
            page_words[anchor_start_page: anchor_end_page + 1]
        )
        token_idx = anchor_offset + effective_anchor_size
        page_idx = anchor_end_page + 1
        next_cursor = anchor_end_page + 1

        # ── Phase 3: forward extension with bounded gap ───────────────
        while token_idx < n and page_idx < len(page_tokens):
            target = remaining_tokens[token_idx]
            window_end = min(page_idx + self.max_gap + 1, len(page_tokens))
            found_at = None

            for j in range(page_idx, window_end):
                if page_tokens[j] == target:
                    found_at = j
                    break

            if found_at is not None:
                matched_words.append(page_words[found_at])
                token_idx += 1
                page_idx = found_at + 1
                next_cursor = found_at + 1
            else:
                break

        coverage = token_idx / n if n > 0 else 0.0
        unmatched = remaining_tokens[token_idx:]

        return matched_words, unmatched, next_cursor, coverage

    def _find_anchor(
        self,
        anchor_tokens: List[str],
        page_tokens: List[str],
        start_from: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Searches for the first position in `page_tokens[start_from:]`
        where `anchor_tokens` appear (nearly) contiguously.

        A gap of at most 1 page-word between consecutive anchor tokens
        is tolerated to absorb hyphenation and inline footnote artefacts.

        Returns:
            (start_index, end_index) in page_tokens, or (None, None).
        """
        n = len(anchor_tokens)
        if n == 0:
            return start_from, start_from

        for i in range(start_from, len(page_tokens)):
            if page_tokens[i] != anchor_tokens[0]:
                continue

            last_pos = i
            matched = 1

            for k in range(1, n):
                found = False
                for gap in (1, 2):  # gap=1 adjacent, gap=2 one word skipped
                    nxt = last_pos + gap
                    if (
                        nxt < len(page_tokens)
                        and page_tokens[nxt] == anchor_tokens[k]
                    ):
                        last_pos = nxt
                        matched += 1
                        found = True
                        break
                if not found:
                    break

            if matched == n:
                return i, last_pos

        return None, None

    def _tokenize(self, text: str) -> List[str]:
        """Splits text into normalised tokens for matching."""
        return [t for t in (self._normalize(w) for w in text.split()) if t]

    def _normalize(self, token: str) -> str:
        """Lowercases and strips surrounding punctuation for robust matching."""
        return token.lower().strip(".,;:!?\"'()[]{}")

    def _convex_hull(self, words: List[dict]) -> List[Point]:
        """
        Computes the convex hull of the bounding boxes of the given words.

        Falls back gracefully:
          - < MIN_POINTS_FOR_HULL unique points -> returns raw corners.
          - Collinear points (QhullError) -> returns axis-aligned bbox.
        """
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

        pts = np.unique(np.array(points, dtype=float), axis=0)

        if len(pts) < self.MIN_POINTS_FOR_HULL:
            return [tuple(p) for p in pts]

        try:
            hull = ConvexHull(pts)
            return [tuple(pts[v]) for v in hull.vertices]
        except Exception:
            x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
            x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
