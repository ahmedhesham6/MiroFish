"""
RSS Source Plugin — fetches articles from an RSS/Atom feed.

Injects article text as documents for ontology generation.
"""

from typing import Any, Dict, List

import feedparser

from app.plugins.sdk import SourcePlugin


class RssSourcePlugin(SourcePlugin):
    """Fetches up to max_items entries from an RSS/Atom feed."""

    def fetch_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and return RSS feed articles as plain-text documents.

        Args:
            config:
                feed_url (str): URL of the RSS or Atom feed.
                max_items (int, optional): Maximum articles to fetch. Default 10.

        Returns:
            {
                "documents": [{"title": ..., "text": ..., "link": ...}, ...],
                "metadata": {"feed_title": ..., "entry_count": ..., "feed_url": ...},
            }
        """
        feed_url: str = config["feed_url"]
        max_items: int = int(config.get("max_items", 10))

        feed = feedparser.parse(feed_url)

        documents: List[Dict[str, Any]] = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            content_list = entry.get("content", [])
            content = content_list[0].get("value", "") if content_list else ""

            # Prefer full content; fall back to summary
            body = content or summary

            # Strip basic HTML tags from body
            body = _strip_tags(body)

            text = f"{title}\n\n{body}".strip()
            if text:
                documents.append({
                    "title": title,
                    "text": text,
                    "link": entry.get("link", ""),
                })

        metadata = {
            "feed_title": feed.feed.get("title", ""),
            "entry_count": len(documents),
            "feed_url": feed_url,
        }

        return {"documents": documents, "metadata": metadata}


def _strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    import re
    return re.sub(r"<[^>]+>", "", text)
