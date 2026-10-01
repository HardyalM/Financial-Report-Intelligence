"""Direction words shared by rendering and validator V7 (one list, so they cannot drift)."""

from __future__ import annotations

_UP_TEXT = """
improved improve improves improving improvement rose rise rises risen rising
increased increase increases increasing grew grow grows grown growing higher
strengthened strengthening expanded climbed gained
"""
UP = frozenset(_UP_TEXT.split())
_DOWN_TEXT = """
fell fall falls fallen falling declined decline declines declining decreased
decrease decreases decreasing weakened weakening lower dropped drop contracted
deteriorated deterioration slipped eroded
"""
DOWN = frozenset(_DOWN_TEXT.split())

DIRECTION_WORDS = UP | DOWN
