import logging

import httpx

logger = logging.getLogger(__name__)

_NEWSAPI_URL = "https://newsapi.org/v2/everything"


_PAKISTAN_TELECOM_KEYWORDS = ("pakistan", "telenor", "jazz", "zong", "pta")


def fetch_news_articles(api_key: str) -> str:
    """
    Fetches recent telecom-related news articles from NewsAPI.org.

    Returns a combined string of article titles and descriptions.
    Returns an empty string when no relevant Pakistan telecom articles are found.
    """
    if not api_key:
        logger.warning("NEWSAPI_KEY is not set — returning empty article text")
        return ""

    try:
        params = {
            "q": "Telenor Pakistan OR Jazz Pakistan OR Zong Pakistan OR Pakistani telecom OR PTA Pakistan telecom",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 5,
            "searchIn": "title,description",
            "apiKey": api_key,
        }

        with httpx.Client(timeout=15.0) as client:
            response = client.get(_NEWSAPI_URL, params=params)
            response.raise_for_status()

        data = response.json()
        articles = data.get("articles", [])
        logger.info("NewsAPI returned %d articles about Pakistan telecom", len(articles))

        if not articles:
            logger.info("No relevant Pakistan telecom articles found, returning empty")
            return ""

        parts: list[str] = []
        for article in articles:
            title = (article.get("title") or "").strip()
            description = (article.get("description") or "").strip()
            if title:
                parts.append(title)
            if description:
                parts.append(description)

        combined = "\n".join(parts).strip()
        if not combined:
            logger.info("No relevant Pakistan telecom articles found, returning empty")
            return ""

        combined_lower = combined.lower()
        if not any(keyword in combined_lower for keyword in _PAKISTAN_TELECOM_KEYWORDS):
            logger.info("No relevant Pakistan telecom articles found, returning empty")
            return ""

        logger.info("Using real articles")
        return combined

    except httpx.HTTPError as exc:
        logger.warning("NewsAPI HTTP error — returning empty article text: %s", exc)
        return ""
    except Exception as exc:
        logger.warning("Unexpected NewsAPI error — returning empty article text: %s", exc)
        return ""
