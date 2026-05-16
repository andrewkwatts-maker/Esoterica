"""Use local LLM to categorize and enrich scraped conspiracy content."""
from __future__ import annotations

from eyecore import LLMClient

CONSPIRACY_CATEGORIES = [
    "government-surveillance",
    "secret-societies",
    "false-flag",
    "extraterrestrial",
    "financial-manipulation",
    "medical-coverup",
    "media-control",
    "religion-occult",
    "geopolitical",
    "technology-control",
    "weather-manipulation",
    "historical-revision",
    "assassination",
    "mind-control",
    "new-world-order",
    "other",
]


def categorize_article(article: dict) -> dict:
    """Add 'category', 'summary', and 'topics' fields to article dict using LLM."""
    llm = LLMClient.get()
    if not llm.is_available():
        return article
    text = (
        f"{article.get('title', '')}\n"
        f"{article.get('summary', article.get('content', ''))[:1000]}"
    )
    article["category"] = llm.categorize(text, CONSPIRACY_CATEGORIES)
    if not article.get("summary") or len(article.get("summary", "")) < 50:
        article["summary"] = llm.summarize(text, max_words=150)
    article["llm_topics"] = llm.extract_topics(text)
    return article


def categorize_batch(articles: list[dict], verbose: bool = False) -> list[dict]:
    """Categorize a list of articles. Returns enriched list."""
    result = []
    for i, article in enumerate(articles):
        if verbose:
            print(f"  Categorizing {i + 1}/{len(articles)}: {article.get('title', '')[:60]}")
        result.append(categorize_article(article))
    return result


def generate_daily_report(articles: list[dict], date: str) -> str:
    """Generate a daily conspiracy report from all articles for a given date."""
    llm = LLMClient.get()
    if not llm.is_available():
        return f"LLM not available — {len(articles)} articles scraped on {date}"

    by_category: dict[str, list] = {}
    for a in articles:
        cat = a.get("category", "other")
        by_category.setdefault(cat, []).append(a)

    top_categories = sorted(
        by_category.items(), key=lambda x: len(x[1]), reverse=True
    )[:5]

    report_parts = [f"# Conspiracy Intelligence Report — {date}\n"]
    for cat, items in top_categories:
        section = llm.generate_report(
            items,
            cat,
            title_field="title",
            body_field="summary",
            max_words=300,
        )
        report_parts.append(f"\n## {cat.replace('-', ' ').title()}\n{section}")

    return "\n".join(report_parts)
