# RSS Source Plugin

Fetches articles from an RSS or Atom feed and injects them as documents for ontology enrichment.

## Plugin Type

`source` — runs before ontology generation, appending fetched article text to the document list.

## Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `feed_url` | string | yes | — | Full URL of the RSS or Atom feed to fetch |
| `max_items` | integer | no | 10 | Maximum number of articles to fetch per run |

## Example Config

```json
{
  "feed_url": "https://feeds.reuters.com/reuters/topNews",
  "max_items": 5
}
```

## Output

Returns a dict with:

- `documents`: list of `{"title": str, "text": str, "link": str}` objects
- `metadata`: `{"feed_title": str, "entry_count": int, "feed_url": str}`

## Dependencies

- `feedparser>=6.0.0` (already in `requirements.txt`)

## Notes

- Strips HTML tags from article bodies.
- Prefers full article content over summary when both are present.
- Entries with no usable text are silently skipped.
