"""Esoterica live content scraper: Reddit, forums, RSS feeds.

Fetching stays in Python -- it waits on sockets, and PRAW and feedparser
already own the protocol details. What is done to the bytes that come back
is Rust: HTML normalisation runs once per scraped item and used to be three
`re.sub` passes each.
"""
from __future__ import annotations

import hashlib
import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from time import mktime
from urllib.parse import urlparse

from eyecore import cache_dir

from ._backend import strip_html, strip_html_batch

_SOURCES_FILE = cache_dir("esoterica") / "sources.json"

DEFAULT_REDDIT_SUBS = [
    "occult",
    "witchcraft",
    "Wicca",
    "magick",
    "chaos_magic",
    "thelema",
    "hermeticism",
    "tarot",
    "spells",
    "paganism",
]

DEFAULT_4CHAN_BOARDS = ["x"]

DEFAULT_FEEDS = [
    {"url": "https://www.llewellyn.com/feed/rss/news", "name": "Llewellyn", "category": "witchcraft"},
    {"url": "https://www.patheos.com/blogs/agora/feed/", "name": "Patheos Agora", "category": "paganism"},
    {"url": "https://witchesandpagans.com/feed", "name": "Witches & Pagans", "category": "witchcraft"},
]


def load_sources() -> dict:
    """Returns dict with keys: reddit_subs, chan_boards, feeds."""
    if _SOURCES_FILE.exists():
        return json.loads(_SOURCES_FILE.read_text(encoding="utf-8"))
    return {
        "reddit_subs": DEFAULT_REDDIT_SUBS,
        "chan_boards": DEFAULT_4CHAN_BOARDS,
        "feeds": DEFAULT_FEEDS,
    }


def save_sources(sources: dict) -> None:
    _SOURCES_FILE.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")


def add_reddit_sub(subreddit: str) -> None:
    """Add a subreddit to the configured list."""
    subreddit = subreddit.lstrip("r/").lstrip("/")
    sources = load_sources()
    subs = sources.setdefault("reddit_subs", list(DEFAULT_REDDIT_SUBS))
    if subreddit not in subs:
        subs.append(subreddit)
        save_sources(sources)


def remove_reddit_sub(subreddit: str) -> bool:
    """Remove a subreddit from the configured list. Returns True if removed."""
    subreddit = subreddit.lstrip("r/").lstrip("/")
    sources = load_sources()
    subs = sources.get("reddit_subs", [])
    if subreddit in subs:
        subs.remove(subreddit)
        sources["reddit_subs"] = subs
        save_sources(sources)
        return True
    return False


def add_feed(url: str, name: str = "", category: str = "conspiracy") -> dict:
    """Add an RSS/Atom feed URL to the configured feed list. Returns the feed entry."""
    if not name:
        parsed = urlparse(url)
        name = parsed.netloc or url
    entry = {"url": url, "name": name, "category": category}
    sources = load_sources()
    feeds = sources.setdefault("feeds", list(DEFAULT_FEEDS))
    if not any(f["url"] == url for f in feeds):
        feeds.append(entry)
        save_sources(sources)
    return entry


def remove_feed(url: str) -> bool:
    """Remove a feed by URL. Returns True if removed."""
    sources = load_sources()
    feeds = sources.get("feeds", [])
    filtered = [f for f in feeds if f["url"] != url]
    if len(filtered) < len(feeds):
        sources["feeds"] = filtered
        save_sources(sources)
        return True
    return False


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


class ScrapeWarning(UserWarning):
    """A source failed during a scrape. Emitted instead of being swallowed."""


def _report_failure(what: str, exc: BaseException, verbose: bool) -> None:
    """Surface a per-source failure. Never silent.

    Each of these handlers used to be `if verbose: print(...)`, so a feed that
    had been 404ing for months was indistinguishable from a feed with no new
    posts unless somebody happened to pass verbose=True. A warning is
    filterable by a caller who genuinely does not care; silence was not.
    """
    message = f"{what}: {type(exc).__name__}: {exc}"
    if verbose:
        print(f"ERROR: {message}")
    warnings.warn(message, ScrapeWarning, stacklevel=3)


def _strip_html(text: str) -> str:
    r"""Remove HTML tags, decode character references, and collapse whitespace.

    Delegates to the Rust core, which is a faithful port of the three
    `re.sub`/`html.unescape` passes this used to run -- including the order
    (tags first, so `&lt;b&gt;` survives as literal text) and CPython's
    definition of `\s`, which counts U+001C..U+001F as whitespace where
    Rust's own `char::is_whitespace` does not.

    Named references outside the crate's table are left verbatim, as are the
    semicolon-less legacy spellings; see `apocrypha_core::entities`.
    """
    if not text:
        return ""
    return strip_html(text)


def _strip_html_many(texts: list[str]) -> list[str]:
    """Normalise a whole list in one crossing of the FFI boundary.

    Same result as calling :func:`_strip_html` on each element -- the crate's
    own tests hold the batch and scalar forms equal -- but a scrape of one
    board or feed pays for one call rather than one per item. An element over
    ``MAX_TEXT_BYTES`` raises `OverflowError` for the whole batch instead of
    being silently replaced, so a truncated article cannot hide among the
    good ones.
    """
    if not texts:
        # The extension accepts an empty batch, but there is no reason to
        # cross the boundary to be told nothing came back.
        return []
    return strip_html_batch(texts)


def scrape_reddit(limit_per_sub: int = 25, verbose: bool = False) -> list[dict]:
    """Scrape hot posts from configured subreddits via PRAW. Returns article dicts."""
    try:
        import praw
    except ImportError:
        print(
            "PRAW not installed. Install with: pip install 'esoterica[scrape]'"
        )
        return []

    import os
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print(
            "Reddit credentials not set. "
            "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.\n"
            "Get credentials at: https://www.reddit.com/prefs/apps"
        )
        return []

    sources = load_sources()
    subreddits = sources.get("reddit_subs", DEFAULT_REDDIT_SUBS)

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="esoterica/1.0 (conspiracy-scraper; read-only)",
            read_only=True,
        )
    except Exception as exc:
        print(f"Failed to initialize Reddit client: {exc}")
        return []

    articles: list[dict] = []

    for sub in subreddits:
        if verbose:
            print(f"  reddit/r/{sub}...", end=" ", flush=True)
        try:
            subreddit = reddit.subreddit(sub)
            count = 0
            for post in subreddit.hot(limit=limit_per_sub):
                url = post.url
                if not url:
                    continue
                title = post.title or ""
                summary = post.selftext[:500] if post.selftext else title
                published = datetime.fromtimestamp(
                    post.created_utc, tz=timezone.utc
                ).isoformat()
                tags = [post.link_flair_text] if post.link_flair_text else []

                payload = {
                    "id": _article_id(url + str(post.id)),
                    "url": url,
                    "title": title,
                    "source": f"reddit/r/{sub}",
                    "category": "conspiracy",
                    "published": published,
                    "summary": summary,
                    "content": post.selftext,
                    "tags": tags,
                    "reddit_id": post.id,
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "subreddit": sub,
                }

                articles.append({
                    "id": payload["id"],
                    "url": url,
                    "title": title,
                    "source": f"reddit/r/{sub}",
                    "category": "conspiracy",
                    "published": published,
                    "summary": summary,
                    "content": post.selftext,
                    "tags": json.dumps(tags),
                    "data": json.dumps(payload, ensure_ascii=False),
                })
                count += 1
            if verbose:
                print(f"{count} posts")
        except Exception as exc:
            # One unreachable subreddit must not lose the other nine, but the
            # failure is reported unconditionally: gating it on `verbose` is
            # how a source that has been dead for months stays invisible.
            _report_failure(f"reddit/r/{sub}", exc, verbose)

    return articles


def scrape_4chan(limit_per_board: int = 20, verbose: bool = False) -> list[dict]:
    """Scrape active threads from 4chan boards via public JSON API."""
    try:
        import requests
    except ImportError:
        print("requests not installed. Install with: pip install 'esoterica[scrape]'")
        return []

    sources = load_sources()
    boards = sources.get("chan_boards", DEFAULT_4CHAN_BOARDS)

    articles: list[dict] = []
    session = requests.Session()
    session.headers.update({"User-Agent": "esoterica/1.0 (conspiracy-scraper; research)"})

    for board in boards:
        if verbose:
            print(f"  4chan/{board}...", end=" ", flush=True)
        try:
            url = f"https://a.4cdn.org/{board}/catalog.json"
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            pages = resp.json()

            # Two passes. The first selects the threads, bounded by the
            # caller's limit; the second normalises every subject and comment
            # in two batch calls instead of three per thread.
            selected: list[dict] = []
            for page in pages:
                if len(selected) >= limit_per_board:
                    break
                for thread in page.get("threads", []):
                    if len(selected) >= limit_per_board:
                        break
                    if not thread.get("no"):
                        continue
                    selected.append(thread)

            subjects = _strip_html_many([t.get("sub") or "" for t in selected])
            comments = _strip_html_many([t.get("com") or "" for t in selected])

            count = 0
            for thread, subject, comment in zip(
                selected, subjects, comments, strict=True
            ):
                thread_no = thread["no"]
                title = subject or comment[:100]
                if not title:
                    title = f"Thread #{thread_no}"

                summary = comment[:500]
                thread_url = f"https://boards.4chan.org/{board}/thread/{thread_no}"
                published = datetime.fromtimestamp(
                    thread.get("time", 0), tz=timezone.utc
                ).isoformat()
                replies = thread.get("replies", 0)
                images = thread.get("images", 0)

                payload = {
                    "id": _article_id(thread_url),
                    "url": thread_url,
                    "title": title,
                    "source": f"4chan/{board}",
                    "category": "conspiracy",
                    "published": published,
                    "summary": summary,
                    "content": summary,
                    "tags": [board],
                    "thread_no": thread_no,
                    "replies": replies,
                    "images": images,
                    "board": board,
                }

                articles.append({
                    "id": payload["id"],
                    "url": thread_url,
                    "title": title,
                    "source": f"4chan/{board}",
                    "category": "conspiracy",
                    "published": published,
                    "summary": summary,
                    "content": summary,
                    "tags": json.dumps([board]),
                    "data": json.dumps(payload, ensure_ascii=False),
                })
                count += 1

            if verbose:
                print(f"{count} threads")

            # Polite delay between boards to respect API
            time.sleep(1)

        except Exception as exc:
            _report_failure(f"4chan/{board}", exc, verbose)

    return articles


def _parse_feed_time(entry) -> str:
    """Parse published time from a feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.fromtimestamp(
                mktime(entry.published_parsed), tz=timezone.utc
            ).isoformat()
        except (OverflowError, OSError, ValueError, TypeError):
            # Named, not blanket: these are what a malformed or out-of-range
            # struct_time raises. Falling back to the raw string is the
            # deliberate recovery. Anything else is a bug and must propagate.
            pass
    return entry.get("published", "")


def scrape_feeds(verbose: bool = False) -> list[dict]:
    """Scrape configured RSS/Atom feeds via feedparser."""
    try:
        import feedparser
    except ImportError:
        print("feedparser not installed. Install with: pip install 'esoterica[scrape]'")
        return []

    sources = load_sources()
    feeds = sources.get("feeds", DEFAULT_FEEDS)
    articles: list[dict] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("name", feed_cfg["url"])
        if verbose:
            print(f"  {label}...", end=" ", flush=True)
        try:
            feed = feedparser.parse(
                feed_cfg["url"],
                agent="esoterica/1.0 (conspiracy-reader)",
            )
            # Entries without a link are dropped first so the batch below is
            # parallel to `usable` by construction.
            usable = [
                (entry, entry.get("link") or entry.get("id", ""))
                for entry in feed.entries
                if entry.get("link") or entry.get("id", "")
            ]
            summaries = _strip_html_many([
                (entry.get("summary") or entry.get("description") or "").strip()
                for entry, _url in usable
            ])

            count = 0
            for (entry, url), summary in zip(usable, summaries, strict=True):
                title = entry.get("title", "Untitled").strip()
                if len(summary) > 3000:
                    summary = summary[:3000]

                published = _parse_feed_time(entry)
                entry_tags = [
                    t.get("term", "") for t in entry.get("tags", []) if t.get("term")
                ]
                category = feed_cfg.get("category", "conspiracy")
                source_name = feed_cfg.get("name", urlparse(url).netloc)

                payload = {
                    "id": _article_id(url),
                    "url": url,
                    "title": title,
                    "source": source_name,
                    "category": category,
                    "published": published,
                    "summary": summary,
                    "tags": entry_tags,
                    "feed_url": feed_cfg["url"],
                }

                articles.append({
                    "id": payload["id"],
                    "url": url,
                    "title": title,
                    "source": source_name,
                    "category": category,
                    "published": published,
                    "summary": summary,
                    "content": "",
                    "tags": json.dumps(entry_tags),
                    "data": json.dumps(payload, ensure_ascii=False),
                })
                count += 1

            if verbose:
                print(f"{count} articles")

        except Exception as exc:
            _report_failure(label, exc, verbose)

    return articles


def scrape_all(verbose: bool = False) -> dict[str, int]:
    """Run all scrapers. Returns {source_type: count}."""
    from ._store import today_db, insert_articles, compress_old_days

    db = today_db()
    results: dict[str, int] = {}

    if verbose:
        print("Scraping Reddit...")
    reddit_articles = scrape_reddit(verbose=verbose)
    reddit_new = insert_articles(db, reddit_articles)
    results["reddit"] = reddit_new
    if verbose:
        print(f"  Reddit total: {reddit_new} new ({len(reddit_articles)} fetched)")

    if verbose:
        print("Scraping 4chan...")
    chan_articles = scrape_4chan(verbose=verbose)
    chan_new = insert_articles(db, chan_articles)
    results["4chan"] = chan_new
    if verbose:
        print(f"  4chan total: {chan_new} new ({len(chan_articles)} fetched)")

    if verbose:
        print("Scraping RSS feeds...")
    feed_articles = scrape_feeds(verbose=verbose)
    feed_new = insert_articles(db, feed_articles)
    results["feeds"] = feed_new
    if verbose:
        print(f"  Feeds total: {feed_new} new ({len(feed_articles)} fetched)")

    db.close()
    compressed = compress_old_days()
    if verbose and compressed:
        print(f"Compressed: {', '.join(compressed)}")

    return results
