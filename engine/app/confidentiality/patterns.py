"""Sensitive-value detectors used by the confidentiality engine.

Custom terms use an Aho-Corasick automaton. Built-in patterns are deliberately
conservative and every detector returns offsets into the original Python string.
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DetectedSpan:
    start: int
    end: int
    match_type: str
    category: str


@dataclass
class _TrieNode:
    children: dict[str, "_TrieNode"] = field(default_factory=dict)
    failure: "_TrieNode | None" = None
    outputs: list[str] = field(default_factory=list)


EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+(?![\w-])"
)
JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:Bearer\s+)?"
    r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"
    r"(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
API_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"sk_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{30,}"
    r")(?![A-Za-z0-9])"
)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d().\-\s]{5,}\d(?!\w)")

_PRIORITY = {"jwt": 0, "api_key": 1, "credit_card": 2, "email": 3, "phone": 4, "custom_term": 5}


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _fold_with_offsets(text: str) -> tuple[str, list[int]]:
    folded_parts: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        folded = char.casefold()
        folded_parts.append(folded)
        offsets.extend([index] * len(folded))
    return "".join(folded_parts), offsets


def _custom_term_spans(text: str, terms: tuple[str, ...] | list[str]) -> list[DetectedSpan]:
    normalized_terms = sorted({term.strip().casefold() for term in terms if term and term.strip()})
    if not normalized_terms:
        return []

    root = _TrieNode()
    root.failure = root
    for term in normalized_terms:
        node = root
        for char in term:
            node = node.children.setdefault(char, _TrieNode())
        node.outputs.append(term)

    queue: deque[_TrieNode] = deque()
    for child in root.children.values():
        child.failure = root
        queue.append(child)

    while queue:
        node = queue.popleft()
        for char, child in node.children.items():
            fallback = node.failure
            while fallback is not root and char not in fallback.children:
                fallback = fallback.failure or root
            child.failure = fallback.children.get(char, root)
            child.outputs.extend(child.failure.outputs)
            queue.append(child)

    folded_text, offsets = _fold_with_offsets(text)
    spans: list[DetectedSpan] = []
    state = root
    for index, char in enumerate(folded_text):
        while state is not root and char not in state.children:
            state = state.failure or root
        state = state.children.get(char, root)
        for term in state.outputs:
            folded_start = index - len(term) + 1
            start = offsets[folded_start]
            end = offsets[index] + 1
            spans.append(DetectedSpan(start, end, "custom_term", "custom_term"))
    return spans


def detect_sensitive_spans(text: str, policy) -> list[DetectedSpan]:
    """Return deduplicated sensitive spans without retaining source values."""
    if not text:
        return []

    candidates = _custom_term_spans(text, policy.custom_terms)
    if policy.redact_jwts:
        candidates.extend(DetectedSpan(m.start(), m.end(), "jwt", "credential") for m in JWT_RE.finditer(text))
    if policy.redact_api_keys:
        candidates.extend(DetectedSpan(m.start(), m.end(), "api_key", "credential") for m in API_KEY_RE.finditer(text))
    if policy.redact_credit_cards:
        candidates.extend(
            DetectedSpan(m.start(), m.end(), "credit_card", "payment_card")
            for m in CARD_RE.finditer(text) if _luhn_valid(m.group())
        )
    if policy.redact_emails:
        candidates.extend(DetectedSpan(m.start(), m.end(), "email", "personal_data") for m in EMAIL_RE.finditer(text))
    if policy.redact_phones:
        for match in PHONE_RE.finditer(text):
            digits = sum(char.isdigit() for char in match.group())
            if 7 <= digits <= 15 and not _luhn_valid(match.group()):
                candidates.append(DetectedSpan(match.start(), match.end(), "phone", "personal_data"))

    # Resolve overlapping detections deterministically: longest span wins,
    # then detector priority. Separate non-overlapping values are all retained.
    candidates.sort(key=lambda item: (item.start, item.end))
    clusters: list[list[DetectedSpan]] = []
    cluster_end = -1
    for candidate in candidates:
        if not clusters or candidate.start >= cluster_end:
            clusters.append([candidate])
            cluster_end = candidate.end
        else:
            clusters[-1].append(candidate)
            cluster_end = max(cluster_end, candidate.end)

    selected = [
        max(cluster, key=lambda item: (item.end - item.start, -_PRIORITY.get(item.match_type, 99), -item.start))
        for cluster in clusters
    ]
    return sorted(selected, key=lambda item: item.start)
