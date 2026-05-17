# esoterica

Magic systems, spells, rituals, arcane traditions, and esoteric knowledge — a curated encyclopedia and live scraper for Python.

## Features

- Curated database of spells, rituals, traditions, grimoires, ingredients, artifacts, and practitioners
- Full-text search with FTS5 fallback to LIKE
- Topic graph linking traditions, practices, and magical concepts
- Live scraper for Reddit, 4chan /x/, and esoteric RSS feeds (optional)
- LLM-powered categorization into 18 magic taxonomy categories (optional)
- Daily rotating local databases with compression
- On-demand corpus checkout (downloaded once, cached locally)

## Installation

```bash
pip install esoterica
```

With scraping support:

```bash
pip install "esoterica[scrape]"   # adds feedparser, requests, beautifulsoup4, praw
```

## Quick start

```python
import esoterica

# Curated database queries
spell      = esoterica.GetSpell("Fireball")
ritual     = esoterica.GetRitual("Lesser Banishing Ritual")
tradition  = esoterica.GetTradition("Hermeticism")
grimoire   = esoterica.GetGrimoire("Key of Solomon")
practioner = esoterica.GetPractitioner("Aleister Crowley")

# Full-text search
results = esoterica.Search("banishment")
western = esoterica.ByTradition("ceremonial-magic")
all_    = esoterica.GetAll("spell")

# Topic graph
related = esoterica.GetRelated("Kabbalah")
topics  = esoterica.GetTopics("elemental")
tree    = esoterica.GetTopicTree("hermeticism")

# Live scraper — configure sources
esoterica.AddFeed("https://www.llewellyn.com/feed/rss/news")
esoterica.AddSubreddit("occult")          # requires REDDIT_CLIENT_ID env var
sources = esoterica.ListSources()

# Scrape and categorize
esoterica.Scrape()                         # fetch from all sources
esoterica.Categorize(verbose=True)         # LLM categorization (requires LLM backend)
report = esoterica.DailyReport()           # generate today's summary report

# Corpus
esoterica.FetchCorpus("gutenberg-key-of-solomon")
hits = esoterica.SearchCorpus("circle of protection")
```

## LLM-powered categorization

When an LLM backend is available, articles are classified into 18 categories:

`Ceremonial Magic`, `Folk Magic`, `Witchcraft`, `Hermeticism`, `Kabbalah`, `Alchemy`, `Divination`, `Shamanism`, `Chaos Magic`, `Druidry`, `Astrology`, `Demonology`, `Angelic Magic`, `Sigils & Symbols`, `Elemental Magic`, `Necromancy`, `Healing Magic`, `Other`

Set `LLM_BACKEND`, `LLM_MODEL`, etc. — see [eyecore](https://github.com/EyesOfAzrael/eyecore#llm-configuration) for configuration.

## Reddit scraping setup

```bash
export REDDIT_CLIENT_ID=your_client_id
export REDDIT_CLIENT_SECRET=your_client_secret
```

Register a read-only script app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).

## Part of the Eyes of Azrael suite

| Package | Description |
|---|---|
| [`eyecore`](https://github.com/EyesOfAzrael/eyecore) | Shared foundation (DB, graph, corpus, LLM) |
| [`azrael`](https://github.com/EyesOfAzrael/azrael) | Mythology encyclopedia |
| [`mnema`](https://github.com/EyesOfAzrael/mnema) | Historical figures and events |
| [`synomosia`](https://github.com/EyesOfAzrael/synomosia) | Conspiracy theories and hidden histories |

## License

MIT — see [LICENSE](LICENSE)
