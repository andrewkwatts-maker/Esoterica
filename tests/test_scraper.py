"""Unit tests for esoterica._scraper — network-free, import-free variants."""
import sys
from unittest.mock import patch, MagicMock

from esoterica._scraper import (
    load_sources,
    scrape_4chan,
    scrape_feeds,
    scrape_reddit,
    DEFAULT_REDDIT_SUBS,
    DEFAULT_4CHAN_BOARDS,
    DEFAULT_FEEDS,
)


# ---------------------------------------------------------------------------
# load_sources — default behaviour (no sources.json on disk)
# ---------------------------------------------------------------------------

def test_load_sources_default():
    """load_sources returns a dict with all three expected keys when no file exists."""
    # Patch _SOURCES_FILE.exists() to return False so defaults are used
    with patch("esoterica._scraper._SOURCES_FILE") as mock_file:
        mock_file.exists.return_value = False
        sources = load_sources()

    assert "reddit_subs" in sources
    assert "chan_boards" in sources
    assert "feeds" in sources
    assert len(sources["reddit_subs"]) > 0
    assert len(sources["chan_boards"]) > 0


def test_load_sources_default_reddit_subs():
    """Default reddit subs include 'conspiracy'."""
    with patch("esoterica._scraper._SOURCES_FILE") as mock_file:
        mock_file.exists.return_value = False
        sources = load_sources()

    assert "occult" in sources["reddit_subs"]


def test_load_sources_default_chan_boards():
    """Default 4chan boards include 'x'."""
    with patch("esoterica._scraper._SOURCES_FILE") as mock_file:
        mock_file.exists.return_value = False
        sources = load_sources()

    assert "x" in sources["chan_boards"]


def test_load_sources_default_feeds_are_dicts():
    """Default feeds are a list of dicts with 'url' keys."""
    with patch("esoterica._scraper._SOURCES_FILE") as mock_file:
        mock_file.exists.return_value = False
        sources = load_sources()

    for feed in sources["feeds"]:
        assert "url" in feed


def test_load_sources_from_file():
    """load_sources reads and parses the sources file when it exists."""
    import json
    fake_sources = {
        "reddit_subs": ["r/test"],
        "chan_boards": ["g"],
        "feeds": [{"url": "https://example.com/feed.xml", "name": "Test", "category": "test"}],
    }
    with patch("esoterica._scraper._SOURCES_FILE") as mock_file:
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = json.dumps(fake_sources)
        sources = load_sources()

    assert sources["reddit_subs"] == ["r/test"]
    assert sources["chan_boards"] == ["g"]


# ---------------------------------------------------------------------------
# scrape_4chan — network unavailable
# ---------------------------------------------------------------------------

def test_scrape_4chan_requests_not_installed():
    """4chan scraper returns [] when requests is not installed."""
    with patch.dict(sys.modules, {"requests": None}):
        result = scrape_4chan()
    assert isinstance(result, list)
    assert result == []


def test_scrape_4chan_returns_list_on_network_error():
    """4chan scraper returns a list (possibly empty) when network requests fail."""
    mock_requests = MagicMock()
    mock_session = MagicMock()
    mock_session.get.side_effect = RuntimeError("simulated network error")
    mock_requests.Session.return_value = mock_session

    with patch.dict(sys.modules, {"requests": mock_requests}):
        result = scrape_4chan()

    assert isinstance(result, list)
    # All boards fail, so result is empty
    assert result == []


def test_scrape_4chan_parses_valid_response():
    """4chan scraper correctly parses a minimal valid catalog response."""
    fake_catalog = [
        {
            "threads": [
                {
                    "no": 12345,
                    "sub": "Test thread",
                    "com": "Some content here",
                    "time": 1700000000,
                    "replies": 5,
                    "images": 2,
                }
            ]
        }
    ]
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = fake_catalog

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    mock_requests = MagicMock()
    mock_requests.Session.return_value = mock_session

    with patch.dict(sys.modules, {"requests": mock_requests}), \
         patch("esoterica._scraper.load_sources") as mock_load, \
         patch("esoterica._scraper.time"):
        mock_load.return_value = {
            "chan_boards": ["x"],
            "reddit_subs": [],
            "feeds": [],
        }
        result = scrape_4chan(limit_per_board=5)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["source"] == "4chan/x"
    assert result[0]["title"] == "Test thread"


# ---------------------------------------------------------------------------
# scrape_reddit — praw not installed / env vars missing
# ---------------------------------------------------------------------------

def test_scrape_reddit_no_praw():
    """Reddit scraper returns [] gracefully when praw is not installed."""
    with patch.dict(sys.modules, {"praw": None}):
        result = scrape_reddit()
    assert isinstance(result, list)
    assert result == []


def test_scrape_reddit_no_credentials():
    """Reddit scraper returns [] when REDDIT_CLIENT_ID/SECRET are not set."""
    mock_praw = MagicMock()
    with patch.dict(sys.modules, {"praw": mock_praw}), \
         patch.dict("os.environ", {"REDDIT_CLIENT_ID": "", "REDDIT_CLIENT_SECRET": ""}, clear=False):
        result = scrape_reddit()
    assert isinstance(result, list)
    assert result == []


def test_scrape_reddit_returns_list():
    """Reddit scraper always returns a list (even on failure)."""
    with patch.dict(sys.modules, {"praw": None}):
        result = scrape_reddit()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# scrape_feeds — feedparser not installed
# ---------------------------------------------------------------------------

def test_scrape_feeds_no_feedparser():
    """Feed scraper returns [] gracefully when feedparser is not installed."""
    with patch.dict(sys.modules, {"feedparser": None}):
        result = scrape_feeds()
    assert isinstance(result, list)
    assert result == []


def test_scrape_feeds_returns_list():
    """Feed scraper always returns a list."""
    with patch.dict(sys.modules, {"feedparser": None}):
        result = scrape_feeds()
    assert isinstance(result, list)


def test_scrape_feeds_parses_valid_feed():
    """Feed scraper correctly parses a minimal valid feedparser result."""
    # Build a plain dict-like entry feedparser would return
    entry_data = {
        "link": "https://example.com/article1",
        "title": "Test Article",
        "summary": "This is a test summary for the feed entry.",
        "tags": [],
    }

    # Use a real dict as the entry; feedparser entries support .get()
    class FeedEntry(dict):
        pass

    mock_entry = FeedEntry(entry_data)

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]

    mock_feedparser = MagicMock()
    mock_feedparser.parse.return_value = mock_feed

    with patch.dict(sys.modules, {"feedparser": mock_feedparser}), \
         patch("esoterica._scraper.load_sources") as mock_load:
        mock_load.return_value = {
            "feeds": [
                {"url": "https://example.com/feed.xml", "name": "TestFeed", "category": "test"}
            ],
            "reddit_subs": [],
            "chan_boards": [],
        }
        result = scrape_feeds()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["title"] == "Test Article"
    assert result[0]["source"] == "TestFeed"


# ---------------------------------------------------------------------------
# DEFAULT constants
# ---------------------------------------------------------------------------

def test_default_reddit_subs_not_empty():
    """DEFAULT_REDDIT_SUBS is a non-empty list of strings."""
    assert isinstance(DEFAULT_REDDIT_SUBS, list)
    assert len(DEFAULT_REDDIT_SUBS) > 0
    for sub in DEFAULT_REDDIT_SUBS:
        assert isinstance(sub, str)
        assert sub.strip()


def test_default_chan_boards_not_empty():
    """DEFAULT_4CHAN_BOARDS is a non-empty list of strings."""
    assert isinstance(DEFAULT_4CHAN_BOARDS, list)
    assert len(DEFAULT_4CHAN_BOARDS) > 0
    for board in DEFAULT_4CHAN_BOARDS:
        assert isinstance(board, str)


def test_default_feeds_have_required_keys():
    """DEFAULT_FEEDS entries all have 'url', 'name', and 'category' keys."""
    for feed in DEFAULT_FEEDS:
        assert "url" in feed
        assert "name" in feed
        assert "category" in feed
        assert feed["url"].startswith("http")
