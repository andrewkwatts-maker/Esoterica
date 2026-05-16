# esoterica

Conspiracy theories, hidden histories, and suppressed knowledge — a curated encyclopedia and live scraper for Python.

## Features

- Curated database of theories, figures, organizations, events, and documents
- Full-text search with FTS5 fallback to LIKE
- Topic graph linking related theories and entities
- Live scraper for Reddit, 4chan boards, and RSS feeds (optional)
- LLM-powered categorization into 16 conspiracy taxonomy categories (optional)
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
theory = esoterica.GetTheory("Illuminati")
figure = esoterica.GetFigure("John F. Kennedy")
org    = esoterica.GetOrganization("Bilderberg Group")

# Full-text search
results = esoterica.Search("shadow government")
orgs    = esoterica.ByCategory("secret-society")
all_    = esoterica.GetAll("theory")

# Topic graph
related = esoterica.GetRelated("New World Order")
topics  = esoterica.GetTopics("government")
tree    = esoterica.GetTopicTree("deep-state")

# Live scraper — configure sources
esoterica.AddFeed("https://conspiracyarchive.com/feed/")
esoterica.AddSubreddit("conspiracy")       # requires REDDIT_CLIENT_ID env var
sources = esoterica.ListSources()

# Scrape and categorize
esoterica.Scrape()                         # fetch from all sources
esoterica.Categorize(verbose=True)         # LLM categorization (requires LLM backend)
report = esoterica.DailyReport()           # generate today's summary report

# Corpus
esoterica.FetchCorpus("gutenberg-1984")
hits = esoterica.SearchCorpus("surveillance")
```

## LLM-powered categorization

When an LLM backend is available, articles are classified into 16 categories:

`Government Control`, `Secret Societies`, `Financial Elites`, `Technology Surveillance`, `Medical Conspiracies`, `Extraterrestrial`, `False Flag Operations`, `Media Manipulation`, `Religious Prophecy`, `Environmental Manipulation`, `Suppressed History`, `Deep State`, `Occult Knowledge`, `Whistleblowers`, `Population Control`, `Cryptids and Anomalies`

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
| [`clio`](https://github.com/EyesOfAzrael/clio) | Historical figures and events |
| [`augur`](https://github.com/EyesOfAzrael/augur) | News aggregation and topic analysis |

## License

MIT — see [LICENSE](LICENSE)
