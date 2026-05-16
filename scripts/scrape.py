#!/usr/bin/env python3
"""Apocrypha conspiracy scraper CLI.

Usage:
    python scripts/scrape.py run [--llm]            # scrape all sources, optionally LLM-categorize
    python scripts/scrape.py reddit                 # scrape Reddit only
    python scripts/scrape.py chan                   # scrape 4chan only
    python scripts/scrape.py feeds                  # scrape RSS feeds only
    python scripts/scrape.py add-feed <url> [--name NAME] [--category CAT]
    python scripts/scrape.py add-sub <subreddit>
    python scripts/scrape.py list                   # list configured sources
    python scripts/scrape.py report [--date DATE]   # generate LLM daily report
    python scripts/scrape.py compress [--keep N]
    python scripts/scrape.py days
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def cmd_run(args) -> None:
    from apocrypha._scraper import scrape_all
    from apocrypha._store import today_db, insert_articles

    print("Scraping all sources...")
    results = scrape_all(verbose=True)
    total = sum(v for v in results.values() if v >= 0)
    print(f"\nSource totals: {results}")
    print(f"Total new articles: {total}")

    if args.llm:
        print("\nRunning LLM categorization...")
        from apocrypha._store import open_day
        from apocrypha._llm_categorizer import categorize_batch
        import json

        db = open_day(date.today().isoformat())
        rows = db.execute("SELECT * FROM articles ORDER BY published DESC").fetchall()
        articles = []
        for r in rows:
            try:
                a = json.loads(r["data"])
            except Exception:
                a = dict(r)
            articles.append(a)

        if not articles:
            print("No articles to categorize.")
            return

        enriched = categorize_batch(articles, verbose=True)
        # Update categories in DB
        updated = 0
        for a in enriched:
            if a.get("category"):
                db.execute(
                    "UPDATE articles SET category=? WHERE id=?",
                    (a["category"], a["id"]),
                )
                updated += 1
        db.commit()
        db.close()
        print(f"\nUpdated {updated} article categories.")


def cmd_reddit(args) -> None:
    from apocrypha._scraper import scrape_reddit
    from apocrypha._store import today_db, insert_articles

    print("Scraping Reddit...")
    articles = scrape_reddit(verbose=True)
    db = today_db()
    new = insert_articles(db, articles)
    db.close()
    print(f"\nDone: {new} new articles ({len(articles)} fetched)")


def cmd_chan(args) -> None:
    from apocrypha._scraper import scrape_4chan
    from apocrypha._store import today_db, insert_articles

    print("Scraping 4chan...")
    articles = scrape_4chan(verbose=True)
    db = today_db()
    new = insert_articles(db, articles)
    db.close()
    print(f"\nDone: {new} new articles ({len(articles)} fetched)")


def cmd_feeds(args) -> None:
    from apocrypha._scraper import scrape_feeds
    from apocrypha._store import today_db, insert_articles

    print("Scraping RSS feeds...")
    articles = scrape_feeds(verbose=True)
    db = today_db()
    new = insert_articles(db, articles)
    db.close()
    print(f"\nDone: {new} new articles ({len(articles)} fetched)")


def cmd_add_feed(args) -> None:
    from apocrypha._scraper import add_feed

    entry = add_feed(args.url, name=args.name or "", category=args.category)
    print(f"Added feed: {entry['name']} -> {entry['url']} [{entry['category']}]")


def cmd_add_sub(args) -> None:
    from apocrypha._scraper import add_reddit_sub

    sub = args.subreddit.lstrip("r/").lstrip("/")
    add_reddit_sub(sub)
    print(f"Added subreddit: r/{sub}")


def cmd_list(args) -> None:
    from apocrypha._scraper import load_sources

    sources = load_sources()

    reddit_subs = sources.get("reddit_subs", [])
    chan_boards = sources.get("chan_boards", [])
    feeds = sources.get("feeds", [])

    print(f"\nReddit subreddits ({len(reddit_subs)}):")
    for sub in reddit_subs:
        print(f"  r/{sub}")

    print(f"\n4chan boards ({len(chan_boards)}):")
    for board in chan_boards:
        print(f"  /{board}/")

    print(f"\nRSS/Atom feeds ({len(feeds)}):")
    for f in feeds:
        print(f"  [{f.get('category', 'conspiracy')}] {f.get('name', '')} -> {f['url']}")


def cmd_report(args) -> None:
    from apocrypha._store import open_day, available_days
    from apocrypha._llm_categorizer import generate_daily_report
    import json

    target_date = args.date or date.today().isoformat()

    try:
        db = open_day(target_date)
    except FileNotFoundError:
        days = available_days()
        if not days:
            print(f"No data available. Run: python scripts/scrape.py run")
        else:
            print(f"No data for {target_date}. Available days: {', '.join(days[:5])}")
        sys.exit(1)

    rows = db.execute("SELECT * FROM articles ORDER BY published DESC").fetchall()
    articles = []
    for r in rows:
        try:
            a = json.loads(r["data"])
        except Exception:
            a = dict(r)
        articles.append(a)
    db.close()

    if not articles:
        print(f"No articles found for {target_date}.")
        sys.exit(1)

    print(f"Generating report for {target_date} ({len(articles)} articles)...")
    report = generate_daily_report(articles, target_date)
    print("\n" + report)


def cmd_compress(args) -> None:
    from apocrypha._store import compress_old_days

    compressed = compress_old_days(keep_uncompressed=args.keep)
    if compressed:
        print(f"Compressed: {', '.join(compressed)}")
    else:
        print("Nothing to compress.")


def cmd_days(args) -> None:
    from apocrypha._store import available_days

    days = available_days()
    if not days:
        print("No data available.")
        return
    for d in days:
        print(f"  {d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="apocrypha conspiracy scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Scrape all sources (Reddit, 4chan, feeds)")
    p_run.add_argument("--llm", action="store_true", help="LLM-categorize scraped articles")

    sub.add_parser("reddit", help="Scrape Reddit subreddits only")
    sub.add_parser("chan", help="Scrape 4chan boards only")
    sub.add_parser("feeds", help="Scrape RSS/Atom feeds only")

    p_add_feed = sub.add_parser("add-feed", help="Add an RSS/Atom feed")
    p_add_feed.add_argument("url", help="Feed URL")
    p_add_feed.add_argument("--name", default="", help="Display name")
    p_add_feed.add_argument("--category", default="conspiracy", help="Category tag")

    p_add_sub = sub.add_parser("add-sub", help="Add a Reddit subreddit")
    p_add_sub.add_argument("subreddit", help="Subreddit name (with or without r/ prefix)")

    sub.add_parser("list", help="List configured sources")

    p_report = sub.add_parser("report", help="Generate LLM daily conspiracy report")
    p_report.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                          help="Date to report on (default: today)")

    p_comp = sub.add_parser("compress", help="Compress old daily DBs")
    p_comp.add_argument("--keep", type=int, default=2,
                        help="Keep N most recent days uncompressed (default: 2)")

    sub.add_parser("days", help="List available day archives")

    args = parser.parse_args()
    {
        "run": cmd_run,
        "reddit": cmd_reddit,
        "chan": cmd_chan,
        "feeds": cmd_feeds,
        "add-feed": cmd_add_feed,
        "add-sub": cmd_add_sub,
        "list": cmd_list,
        "report": cmd_report,
        "compress": cmd_compress,
        "days": cmd_days,
    }[args.command](args)


if __name__ == "__main__":
    main()
