"""News NLP: entity extraction, sentiment analysis, and semantic clustering.

Lightweight implementation with zero heavy ML dependencies.
VADER (vaderSentiment) is optional — falls back to lexicon-based scoring.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

# ── Entity Dictionaries ──────────────────────────────────────────────

COUNTRIES: dict[str, list[str]] = {
    "us": ["united states", "usa", "america", "u.s.", "u.s"],
    "cn": ["china", "prc", "chinese mainland"],
    "jp": ["japan", "nippon"],
    "de": ["germany", "deutschland", "german"],
    "uk": ["united kingdom", "britain", "england", "u.k."],
    "fr": ["france"],
    "in": ["india"],
    "ru": ["russia"],
    "br": ["brazil"],
    "kr": ["south korea", "korea"],
}

ORGANIZATIONS: dict[str, list[str]] = {
    "fed": ["federal reserve", "fed"],
    "ecb": ["european central bank", "ecb"],
    "imf": ["international monetary fund", "imf"],
    "opec": ["opec", "organization of petroleum exporting countries"],
    "brics": ["brics"],
    "ubs": ["ubs"],
    "gs": ["goldman sachs"],
    "jpm": ["jpmorgan", "jpmorgan chase", "jp morgan"],
    "ms": ["morgan stanley"],
    "boa": ["bank of america"],
}

PERSON_TITLES = r"(president|chairman|ceo|secretary|governor|minister|chancellor|commissioner)"

STOCK_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract countries, organizations, people, and stock tickers from text."""
    result: dict[str, list[str]] = {"countries": [], "organizations": [], "people": [], "tickers": []}
    lower = text.lower()

    for code, aliases in COUNTRIES.items():
        if any(alias in lower for alias in aliases):
            result["countries"].append(code.upper())

    for org_id, names in ORGANIZATIONS.items():
        if any(name in lower for name in names):
            result["organizations"].append(org_id.upper())

    person_matches = re.finditer(rf"{PERSON_TITLES}\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    for m in person_matches:
        result["people"].append(m.group(0).strip())

    stock_matches = STOCK_PATTERN.findall(text)
    stop_words = {"THE", "THIS", "THAT", "FOR", "ARE", "WAS", "HAS", "NOT", "BUT", "ALL", "ITS", "CAN", "USD", "EUR", "GBP", "JPY", "CNY"}
    for sym in stock_matches:
        if sym not in stop_words and sym not in result["tickers"]:
            result["tickers"].append(sym)

    return result


# ── Sentiment Analysis ─────────────────────────────────────────────

FINANCIAL_LEXICON: dict[str, float] = {
    "bullish": 0.8, "bearish": -0.8, "outperform": 0.6, "underperform": -0.6,
    "upgrade": 0.5, "downgrade": -0.5, "beat": 0.7, "miss": -0.7,
    "positive": 0.5, "negative": -0.5, "growth": 0.4, "decline": -0.4,
    "profit": 0.6, "loss": -0.6, "expansion": 0.5, "contraction": -0.5,
    "exceed": 0.6, "fall short": -0.6, "surge": 0.7, "plunge": -0.7,
    "rally": 0.6, "sell-off": -0.6, "recovery": 0.5, "recession": -0.8,
    "stable": 0.2, "volatile": -0.3, "uncertainty": -0.4, "confidence": 0.4,
    "overweight": 0.4, "underweight": -0.4, "buy": 0.5, "sell": -0.5,
    "overbought": -0.4, "oversold": 0.3, "breakout": 0.6, "breakdown": -0.6,
    "momentum": 0.3, "resistance": -0.2, "support": 0.3,
}

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER_AVAILABLE = True
except ImportError:
    _VADER_AVAILABLE = False


def _lexicon_score(text: str) -> float:
    lower = text.lower()
    score = 0.0
    matches = 0
    for word, val in FINANCIAL_LEXICON.items():
        if word in lower:
            score += val
            matches += 1
    if matches:
        return max(-1.0, min(1.0, score / math.sqrt(matches)))
    return 0.0


def analyze_sentiment(texts: list[str]) -> dict[str, Any]:
    scores: list[float] = []
    for text in texts:
        if _VADER_AVAILABLE and text.strip():
            try:
                analyzer = SentimentIntensityAnalyzer()
                vs = analyzer.polarity_scores(text)
                scores.append(vs["compound"])
            except Exception:
                scores.append(_lexicon_score(text))
        else:
            scores.append(_lexicon_score(text))

    if not scores:
        return {"overall_score": 0.0, "sentiment": "NEUTRAL", "bullish": 0, "bearish": 0, "neutral": 0}

    overall = sum(scores) / len(scores)
    bullish = sum(1 for s in scores if s > 0.05)
    bearish = sum(1 for s in scores if s < -0.05)
    neutral = len(scores) - bullish - bearish

    if overall > 0.1:
        sentiment = "BULLISH"
    elif overall < -0.1:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    return {
        "overall_score": round(overall, 4),
        "sentiment": sentiment,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": len(scores),
        "vader_used": _VADER_AVAILABLE,
    }


# ── Semantic Clustering ────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "to", "of", "in", "for", "on", "at", "by", "with", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "that", "this",
    "it", "its", "we", "they", "he", "she", "what", "which", "who", "whom",
})

_SYNONYM_MAP = {
    "fed": "federal_reserve", "fomc": "federal_reserve", "jerome powell": "federal_reserve",
    "ecb": "european_central_bank", "lagarde": "european_central_bank",
    "boj": "bank_of_japan", "boc": "bank_of_canada", "boe": "bank_of_england",
}


def _tokenize(text: str) -> list[str]:
    lower = text.lower()
    tokens = re.findall(r"[a-z]+", lower)
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _tf_vector(tokens: list[str], vocab: dict[str, int]) -> list[float]:
    vec = [0.0] * len(vocab)
    counter = Counter(tokens)
    for token, count in counter.items():
        idx = vocab.get(token)
        if idx is not None:
            vec[idx] = 1.0 + math.log(count)
    return vec


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na * nb == 0:
        return 0.0
    return dot / (na * nb)


def cluster_semantic(texts: list[str], threshold: float = 0.25) -> list[list[int]]:
    if not texts:
        return []

    normalized = []
    for t in texts:
        lower = t.lower()
        for src, dst in _SYNONYM_MAP.items():
            lower = lower.replace(src, dst)
        normalized.append(lower)

    tokenized = [_tokenize(t) for t in normalized]
    vocab: dict[str, int] = {}
    for tokens in tokenized:
        for token in tokens:
            if token not in vocab:
                vocab[token] = len(vocab)

    vectors = [_tf_vector(t, vocab) for t in tokenized]

    clusters: list[list[int]] = []
    assigned = set()
    for i in range(len(texts)):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in range(i + 1, len(texts)):
            if j in assigned:
                continue
            sim = _cosine_sim(vectors[i], vectors[j])
            if sim >= threshold:
                cluster.append(j)
                assigned.add(j)
        clusters.append(cluster)

    clusters.sort(key=lambda c: len(c), reverse=True)
    return clusters
