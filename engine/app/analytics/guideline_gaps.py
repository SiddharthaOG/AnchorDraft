"""Version-aware guideline-gap analytics and deterministic reason clustering."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

MIN_DECISIONS = 5
MIN_DISMISSAL_RATE = 0.50
MIN_CLUSTER_SIZE = 2
MAX_REASON_EXAMPLES = 5
MAX_REASON_CHARS = 500

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by",
    "for", "from", "i", "in", "is", "it", "its", "just", "of", "on",
    "or", "our", "so", "that", "the", "their", "this", "to", "we",
    "was", "with", "would", "you", "your",
}


def _tokens(value: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", value.casefold())
    return frozenset(word for word in words if len(word) > 1 and word not in _STOP_WORDS)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def cluster_dismissal_reasons(
    reasons: Iterable[str],
    *,
    similarity_threshold: float = 0.34,
) -> list[dict[str, Any]]:
    """Cluster similar reasons deterministically using token Jaccard similarity."""
    cleaned = sorted(
        [reason.strip()[:MAX_REASON_CHARS] for reason in reasons if isinstance(reason, str) and reason.strip()],
        key=lambda item: (item.casefold(), item),
    )
    clusters: list[dict[str, Any]] = []

    for reason in cleaned:
        tokens = _tokens(reason)
        best_index = None
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            score = max((_similarity(tokens, member) for member in cluster["token_sets"]), default=0.0)
            if score >= similarity_threshold and score > best_score:
                best_index, best_score = index, score
        if best_index is None:
            clusters.append({"token_sets": [tokens], "reasons": [reason]})
        else:
            clusters[best_index]["token_sets"].append(tokens)
            clusters[best_index]["reasons"].append(reason)

    output = []
    for cluster in clusters:
        terms: dict[str, int] = defaultdict(int)
        for token_set in cluster["token_sets"]:
            for token in token_set:
                terms[token] += 1
        theme_terms = [
            term for term, count in sorted(terms.items(), key=lambda item: (-item[1], item[0]))
            if count >= 2
        ][:3]
        output.append({
            "theme": " / ".join(theme_terms) if theme_terms else "Similar feedback",
            "count": len(cluster["reasons"]),
            "examples": cluster["reasons"][:MAX_REASON_EXAMPLES],
            "qualifies": len(cluster["reasons"]) >= MIN_CLUSTER_SIZE,
        })
    return sorted(output, key=lambda item: (-item["count"], item["theme"].casefold()))


def summarize_rule_decisions(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build version-aware metrics from latest-decision rows for one active rule."""
    decisions = [row for row in rows if row.get("action") in {"accept", "edit", "dismiss"}]
    dismissed = [row for row in decisions if row.get("action") == "dismiss"]
    count = len(decisions)
    dismissal_rate = len(dismissed) / count if count else 0.0
    clusters = cluster_dismissal_reasons(row.get("reason") or "" for row in dismissed)
    return {
        "decided": count,
        "dismissed": len(dismissed),
        "acted_on": sum(row.get("action") in {"accept", "edit"} for row in decisions),
        "dismissal_rate": round(dismissal_rate, 4),
        "reason_clusters": clusters,
        "source_versions": sorted({
            int(row["source_version"]) for row in decisions if row.get("source_version") is not None
        }),
        "is_gap": (
            count >= MIN_DECISIONS
            and dismissal_rate >= MIN_DISMISSAL_RATE
            and any(cluster["qualifies"] for cluster in clusters)
        ),
    }


def validate_suggestion_payload(value: Any, current_text: str) -> tuple[str, str]:
    """Validate untrusted provider output and return bounded suggestion fields."""
    if not isinstance(value, dict):
        raise ValueError("Suggestion response must be an object")
    suggested = value.get("suggested_text")
    explanation = value.get("explanation")
    if not isinstance(suggested, str) or not suggested.strip():
        raise ValueError("Suggestion text is missing")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("Suggestion explanation is missing")
    suggested = suggested.strip()
    explanation = explanation.strip()
    if len(suggested) > 500 or len(explanation) > 1000:
        raise ValueError("Suggestion response exceeds allowed length")
    if suggested.casefold() == current_text.strip().casefold():
        raise ValueError("Suggestion does not change the guideline")
    return suggested, explanation
