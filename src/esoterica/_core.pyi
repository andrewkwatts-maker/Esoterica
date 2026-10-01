"""Type stubs for the compiled extension built from the `apocrypha_core` crate.

Every function raises rather than returning a default on bad input:
`OverflowError` when an argument exceeds one of the bounds below, `ValueError`
for a `limit` of zero.
"""

VERSION: str
MAX_TEXT_BYTES: int
MAX_BATCH_LEN: int
MAX_TAGS: int

WEIGHT_NAME_PREFIX: float
WEIGHT_NAME_SUBSTRING: float
WEIGHT_DESCRIPTION: float
WEIGHT_SEARCH_TEXT: float
WEIGHT_FUZZY: float

def is_rust_backend() -> bool: ...
def version_rust() -> str: ...
def score_entity(
    name: str, description: str, search_text: str, query: str
) -> float: ...
def tags_match(tags: list[str], query: str) -> bool: ...
def is_subsequence(text: str, pattern: str) -> bool: ...
def rank_entities(
    rows: list[tuple[str, str, str]], query: str, limit: int = 20
) -> list[tuple[int, float]]: ...
def strip_html(text: str) -> str: ...
def strip_html_batch(texts: list[str]) -> list[str]: ...
