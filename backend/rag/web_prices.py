"""Live, source-backed competitor-price lookup through Ollama's web APIs.

This is deliberately separate from vector retrieval: it is called only for explicit
competitor/current-price questions and only publishes INR prices found in fetched page text.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from backend.config import Settings

_SEARCH_URL = "https://ollama.com/api/web_search"
_FETCH_URL = "https://ollama.com/api/web_fetch"
_PRICE_RE = re.compile(r"(?:₹\s*|\bINR\s*|\bRs\.?\s*)([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]{3,7})(?![0-9])", re.I)
_LIVE_QUESTION_RE = re.compile(
    r"\b(competitor|competitors|market price|market rate|cheaper|current price|price online|"
    r"khadi india|fabindia|jaypore)\b|\b(?:price|cost)\b.{0,32}\belsewhere\b", re.I
)
_STOP_WORDS = {"with", "from", "the", "and", "for", "handmade", "handcrafted", "product", "india"}
_PREFERRED_DOMAINS = ("khadiindia.gov.in", "indiahandloombrand.gov.in", ".gov.in", "nhdc.org.in", "amazon.in", "flipkart.com", "jaypore.com")


def is_live_competitor_question(question: str) -> bool:
    """Return true only for explicit live/comparative-price intent, not ordinary RAG queries."""
    return bool(_LIVE_QUESTION_RE.search(question))


def _headers(settings: Settings) -> dict[str, str]:
    assert settings.ollama_api_key is not None
    return {"Authorization": f"Bearer {settings.ollama_api_key.get_secret_value()}", "Content-Type": "application/json"}


def _relevant(text: str, product: dict) -> bool:
    haystack = text.casefold()
    words = [
        word for word in re.findall(r"[a-z0-9]+", product["name"].casefold())
        if len(word) >= 4 and word not in _STOP_WORDS
    ]
    overlap = sum(word in haystack for word in set(words))
    craft = str(product.get("craft") or "").casefold()
    return overlap >= 2 or (overlap >= 1 and bool(craft) and craft in haystack)


def _preferred(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return any(host == domain or host.endswith(domain) for domain in _PREFERRED_DOMAINS)


def _competitor_name(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    label = host.split(".")[0].casefold() if host else ""
    known = {
        "khadiindia": "Khadi India", "fabindia": "Fabindia", "jaypore": "Jaypore",
        "amazon": "Amazon", "flipkart": "Flipkart", "adityablueartpottery": "Aditya Blue Art Pottery",
    }
    return known.get(label, label.replace("-", " ").title() if label else "Online retailer")


_NOT_A_PRODUCT_PRICE = re.compile(
    r"(shipping|delivery|orders?\s+(?:above|over|of)|min(?:imum)?\s+order|discount|cashback|coupon|\bemi\b|"
    r"per month|/month|wallet|reward|\bsave\b|(?:above|over|under|below|upto|up to)\s*$)", re.I,
)
_AFTER_NOT_PRICE = re.compile(r"^\W{0,3}(off|cashback|discount|/month|per month)\b", re.I)
_MAX_FETCHES = 3


def _price_value(match: re.Match) -> int | None:
    try:
        value = int(float(match.group(1).replace(",", "")))
    except ValueError:
        return None
    return value if 50 <= value <= 10_000_000 else None


def _name_words(product: dict) -> list[str]:
    return [
        word for word in re.findall(r"[a-z0-9]+", str(product.get("name", "")).casefold())
        if len(word) >= 4 and word not in _STOP_WORDS
    ]


def _page_price(content: str, product: dict | None = None, title: str = "") -> tuple[int, str] | None:
    """Return (price, evidence excerpt) for an INR price that is really on the fetched page.

    Accepted only when the price sits within ~250 characters of text naming the product, or -
    on a page whose own title names the product - it is the first plausible price near the top
    of the page (the listing price of a product page). Amounts that read as shipping
    thresholds, discounts, EMIs or coupons are skipped. The excerpt is the page's own text
    around the price and is shown to the user as evidence.
    """
    words = set(_name_words(product or {}))
    needed = min(2, len(words))
    lowered = content.casefold()
    title_names_product = bool(words) and sum(word in title.casefold() for word in words) >= needed
    for match in _PRICE_RE.finditer(content):
        value = _price_value(match)
        if value is None:
            continue
        before = content[max(0, match.start() - 40):match.start()]
        after = content[match.end():match.end() + 15]
        if _NOT_A_PRODUCT_PRICE.search(before) or _AFTER_NOT_PRICE.search(after):
            continue
        if words:
            window = lowered[max(0, match.start() - 250):match.end() + 120]
            near_name = sum(word in window for word in words) >= needed
            if not near_name and not (title_names_product and match.start() < 1500):
                continue
        start, end = max(0, match.start() - 120), min(len(content), match.end() + 60)
        excerpt = content[start:end]
        if start > 0:  # never start or end the quoted evidence mid-word
            excerpt = "…" + excerpt.split(None, 1)[-1] if " " in excerpt else excerpt
        if end < len(content) and " " in excerpt:
            excerpt = excerpt.rsplit(None, 1)[0] + "…"
        excerpt = " ".join(excerpt.split())
        return value, excerpt
    return None


def retrieve_live_competitor_price(
    settings: Settings, product: dict, question: str
) -> tuple[dict | None, str | None]:
    """Search and fetch candidate pages; return only an explicit, relevant INR price.

    The model is not asked to synthesize a price.  Unavailable or ambiguous results return a
    safe explanatory note and never disrupt the local RAG answer.
    """
    if not settings.ollama_web_search_enabled:
        return None, "Live competitor research is disabled."
    if not settings.uses_ollama_cloud or settings.ollama_api_key is None:
        return None, "Live competitor research is not configured; the Kalakriti answer is still available."

    product_name = str(product.get("name", "")).strip()
    if not product_name:
        return None, "Please name one catalogue product to compare."
    terms = [product_name, str(product.get("region", "")), str(product.get("city", "")), str(product.get("craft", "")), "India INR price"]
    brand = re.search(r"\b(Khadi India|Fabindia|Jaypore)\b", question, re.I)
    if brand:
        terms.append(brand.group(1))
    query = " ".join(term for term in terms if term)
    headers = _headers(settings)
    timeout = settings.ollama_web_timeout_seconds

    try:
        response = httpx.post(_SEARCH_URL, headers=headers, json={"query": query, "max_results": 5}, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results", [])
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return None, "Live competitor search is temporarily unavailable; no current price was verified."

    candidates = [row for row in results if isinstance(results, list) and isinstance(row, dict) and isinstance(row.get("url"), str)]
    candidates.sort(key=lambda row: not _preferred(row["url"]))
    fetches = 0
    for result in candidates:
        if fetches >= _MAX_FETCHES:
            break
        url = result["url"]
        if urlparse(url).scheme not in {"https", "http"} or not urlparse(url).hostname:
            continue
        fetches += 1
        try:
            fetched = httpx.post(_FETCH_URL, headers=headers, json={"url": url}, timeout=timeout)
            fetched.raise_for_status()
            page = fetched.json()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            continue
        title = str(page.get("title") or result.get("title") or "").strip()
        content = str(page.get("content") or "")
        page_text = f"{title}\n{content}"
        if not _relevant(page_text, product):
            continue
        found = _page_price(content, product, title)
        if found is None:
            continue
        price, evidence = found
        meaningful_name_words = [
            word for word in re.findall(r"[a-z0-9]+", product_name.casefold())
            if len(word) >= 4 and word not in _STOP_WORDS
        ]
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
        normalized_product_name = re.sub(r"[^a-z0-9]+", " ", product_name.casefold()).strip()
        exact_name = bool(normalized_product_name) and normalized_product_name in normalized_title
        return {
            "competitor_name": _competitor_name(url),
            "competitor_product_name": title or str(result.get("title") or product_name),
            "competitor_price_inr": price,
            "source_url": url,
            "price_checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "comparison_type": "same_product" if exact_name else "comparable_category",
            "price_verified": True,
            "verification_status": "verified_from_fetched_page",
            "source_name": (urlparse(url).hostname or "").removeprefix("www."),
            "evidence": evidence[:300],
        }, None

    return None, "A current comparable competitor price could not be verified from the available pages."
