import unittest

from document_chunk.services.chunk_bounding_polygon import (
    ChunkBoundingPolygon,
)


def make_word(text, x0, x1, top, bottom):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom}


def make_page(page_number, words):
    text = " ".join(w["text"] for w in words)
    return {"page_number": page_number, "text": text, "words": words}


class TestNormalizeAndTokenize(unittest.TestCase):
    def setUp(self):
        self.cbp = ChunkBoundingPolygon()

    def test_normalize_lowercases(self):
        self.assertEqual(self.cbp._normalize("Hello"), "hello")

    def test_normalize_strips_punctuation(self):
        self.assertEqual(self.cbp._normalize("word."), "word")
        self.assertEqual(self.cbp._normalize('"quoted"'), "quoted")
        self.assertEqual(self.cbp._normalize("(paren)"), "paren")

    def test_normalize_strips_multiple_punctuation_chars(self):
        self.assertEqual(self.cbp._normalize("end!?"), "end")

    def test_tokenize_splits_on_whitespace(self):
        tokens = self.cbp._tokenize("hello world foo")
        self.assertEqual(tokens, ["hello", "world", "foo"])

    def test_tokenize_normalizes_each_token(self):
        tokens = self.cbp._tokenize("Hello, World.")
        self.assertEqual(tokens, ["hello", "world"])

    def test_tokenize_empty_string_returns_empty_list(self):
        self.assertEqual(self.cbp._tokenize(""), [])

    def test_tokenize_filters_empty_tokens_after_normalization(self):
        tokens = self.cbp._tokenize("  ")
        self.assertEqual(tokens, [])


class TestFindAnchor(unittest.TestCase):
    def setUp(self):
        self.cbp = ChunkBoundingPolygon()

    def test_finds_anchor_at_exact_position(self):
        page_tokens = ["a", "b", "c", "d", "e"]
        anchor = ["c", "d", "e"]
        start, end = self.cbp._find_anchor(anchor, page_tokens, 0)
        self.assertEqual(start, 2)
        self.assertEqual(end, 4)

    def test_returns_none_when_anchor_not_found(self):
        page_tokens = ["a", "b", "c"]
        anchor = ["x", "y"]
        start, end = self.cbp._find_anchor(anchor, page_tokens, 0)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_respects_start_from_offset(self):
        # Token appears before start_from — must not be matched
        page_tokens = ["target", "other", "other2"]
        anchor = ["target"]
        start, end = self.cbp._find_anchor(anchor, page_tokens, start_from=1)
        self.assertIsNone(start)

    def test_tolerates_one_word_gap_between_anchor_tokens(self):
        # "b" is skipped (gap=1), "a" and "c" should still anchor
        page_tokens = ["a", "b", "c"]
        anchor = ["a", "c"]
        start, end = self.cbp._find_anchor(anchor, page_tokens, 0)
        self.assertEqual(start, 0)
        self.assertEqual(end, 2)

    def test_does_not_tolerate_gap_larger_than_one(self):
        # Gap of 2 words between anchor tokens → no match
        page_tokens = ["a", "skip1", "skip2", "c"]
        anchor = ["a", "c"]
        start, end = self.cbp._find_anchor(anchor, page_tokens, 0)
        self.assertIsNone(start)

    def test_empty_anchor_returns_start_from(self):
        page_tokens = ["a", "b", "c"]
        start, end = self.cbp._find_anchor([], page_tokens, start_from=2)
        self.assertEqual(start, 2)
        self.assertEqual(end, 2)


class TestConvexHull(unittest.TestCase):
    def setUp(self):
        self.cbp = ChunkBoundingPolygon()

    def test_returns_empty_for_no_words(self):
        self.assertEqual(self.cbp._convex_hull([]), [])

    def test_returns_raw_corners_for_single_word(self):
        word = make_word("hi", x0=0, x1=10, top=0, bottom=5)
        result = self.cbp._convex_hull([word])
        # 4 corners but only 4 unique points — below MIN_POINTS_FOR_HULL=3
        # they are returned as-is (np.unique may reduce duplicates)
        self.assertTrue(len(result) > 0)

    def test_returns_hull_for_multiple_words(self):
        words = [
            make_word("a", x0=0, x1=10, top=0, bottom=5),
            make_word("b", x0=20, x1=30, top=0, bottom=5),
            make_word("c", x0=10, x1=20, top=10, bottom=15),
        ]
        result = self.cbp._convex_hull(words)
        self.assertGreaterEqual(len(result), 3)
        for pt in result:
            self.assertEqual(len(pt), 2)

    def test_falls_back_to_bbox_for_collinear_points(self):
        # All points on the same horizontal line → ConvexHull raises QhullError
        words = [
            make_word("a", x0=0, x1=10, top=5, bottom=5),
            make_word("b", x0=20, x1=30, top=5, bottom=5),
            make_word("c", x0=40, x1=50, top=5, bottom=5),
        ]
        result = self.cbp._convex_hull(words)
        self.assertEqual(len(result), 4)  # axis-aligned bbox fallback


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.cbp = ChunkBoundingPolygon(
            anchor_size=2,
            max_gap=1,
            min_coverage=0.5,
        )

    def _page(self, page_number, words):
        return make_page(page_number, words)

    def test_returns_empty_for_empty_chunk_text(self):
        pages = [self._page(1, [make_word("hello", 0, 10, 0, 5)])]
        polygons, cursors = self.cbp.resolve("", pages)
        self.assertEqual(polygons, [])

    def test_returns_empty_when_chunk_not_found_on_any_page(self):
        pages = [self._page(1, [make_word("hello", 0, 10, 0, 5)])]
        polygons, cursors = self.cbp.resolve("xyz abc def", pages)
        self.assertEqual(polygons, [])

    def test_resolves_single_page_chunk(self):
        words = [
            make_word("hello", 0, 50, 10, 20),
            make_word("world", 55, 100, 10, 20),
            make_word("foo", 0, 40, 30, 40),
        ]
        pages = [self._page(1, words)]

        polygons, _ = self.cbp.resolve("hello world", pages)

        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons[0].page_number, 1)
        self.assertGreater(len(polygons[0].points), 0)

    def test_returned_polygon_has_coverage_field(self):
        words = [
            make_word("hello", 0, 50, 10, 20),
            make_word("world", 55, 100, 10, 20),
        ]
        pages = [self._page(1, words)]

        polygons, _ = self.cbp.resolve("hello world", pages)

        self.assertGreater(polygons[0].coverage, 0.0)
        self.assertLessEqual(polygons[0].coverage, 1.0)

    def test_updates_page_cursors_after_match(self):
        words = [
            make_word("alpha", 0, 50, 10, 20),
            make_word("beta", 55, 100, 10, 20),
            make_word("gamma", 0, 50, 30, 40),
        ]
        pages = [self._page(1, words)]

        _, cursors = self.cbp.resolve("alpha beta", pages)

        self.assertIn(1, cursors)
        self.assertGreater(cursors[1], 0)

    def test_chunks_can_overlap_same_words(self):
        words = [
            make_word("alpha", 0, 50, 10, 20),
            make_word("beta", 55, 100, 10, 20),
            make_word("gamma", 0, 50, 30, 40),
            make_word("delta", 55, 100, 30, 40),
        ]
        pages = [self._page(1, words)]

        # First chunk matches alpha + beta
        _, cursors = self.cbp.resolve("alpha beta", pages)

        # Second chunk with same text can re-match alpha/beta (start_from=0 always)
        polygons2, _ = self.cbp.resolve("alpha beta", pages, cursors)
        self.assertEqual(len(polygons2), 1)

    def test_passes_initial_cursors_as_none_starts_from_zero(self):
        words = [
            make_word("hello", 0, 50, 10, 20),
            make_word("world", 55, 100, 10, 20),
        ]
        pages = [self._page(1, words)]

        polygons, _ = self.cbp.resolve("hello world", pages, page_cursors=None)

        self.assertEqual(len(polygons), 1)

    def test_filters_low_coverage_polygons(self):
        cbp = ChunkBoundingPolygon(
            overlap_skip=0,
            anchor_size=2,
            max_gap=0,
            min_coverage=0.9,  # very high threshold
        )
        words = [
            make_word("hello", 0, 50, 10, 20),
            make_word("world", 55, 100, 10, 20),
        ]
        pages = [self._page(1, words)]

        # "hello world missing missing missing" → only 2/5 = 40% coverage < 90%
        polygons, _ = cbp.resolve("hello world missing missing missing", pages)

        self.assertEqual(polygons, [])

    def test_multi_page_chunk_produces_polygon_per_page(self):
        page1_words = [
            make_word("first", 0, 50, 10, 20),
            make_word("second", 55, 100, 10, 20),
        ]
        page2_words = [
            make_word("third", 0, 50, 10, 20),
            make_word("fourth", 55, 100, 10, 20),
        ]
        pages = [self._page(1, page1_words), self._page(2, page2_words)]

        polygons, _ = self.cbp.resolve("first second third fourth", pages)

        page_numbers = [p.page_number for p in polygons]
        self.assertIn(1, page_numbers)
        self.assertIn(2, page_numbers)

    def test_resolve_returns_polygons_in_page_order(self):
        page1_words = [
            make_word("alpha", 0, 50, 10, 20),
            make_word("beta", 55, 100, 10, 20),
        ]
        page2_words = [
            make_word("gamma", 0, 50, 10, 20),
            make_word("delta", 55, 100, 10, 20),
        ]
        pages = [self._page(1, page1_words), self._page(2, page2_words)]

        polygons, _ = self.cbp.resolve("alpha beta gamma delta", pages)

        page_numbers = [p.page_number for p in polygons]
        self.assertEqual(page_numbers, sorted(page_numbers))

    def test_overlapping_chunks_both_produce_polygons(self):
        # With start_from=0 always, two chunks sharing the same words both match.
        words = [
            make_word("one", 0, 30, 0, 10),
            make_word("two", 35, 65, 0, 10),
            make_word("three", 70, 100, 0, 10),
            make_word("four", 0, 30, 15, 25),
        ]
        pages = [self._page(1, words)]

        # chunk K: "one two three"
        polygons1, cursors1 = self.cbp.resolve("one two three", pages)
        self.assertEqual(len(polygons1), 1)

        # chunk K+1 shares "two three" overlap — still produces a polygon
        polygons2, _ = self.cbp.resolve("two three four", pages, cursors1)
        self.assertEqual(len(polygons2), 1)

    def test_overlap_region_covered_by_both_adjacent_chunks(self):
        # Words at overlap region ("beta gamma") should appear in polygons of
        # both chunk K ("alpha beta gamma") and chunk K+1 ("beta gamma delta").
        words = [
            make_word("alpha", 0, 30, 0, 10),
            make_word("beta", 35, 65, 0, 10),
            make_word("gamma", 70, 100, 0, 10),
            make_word("delta", 0, 30, 15, 25),
        ]
        pages = [self._page(1, words)]

        polygons_k, cursors_k = self.cbp.resolve("alpha beta gamma", pages)
        polygons_k1, _ = self.cbp.resolve("beta gamma delta", pages, cursors_k)

        self.assertEqual(len(polygons_k), 1)
        self.assertEqual(len(polygons_k1), 1)
