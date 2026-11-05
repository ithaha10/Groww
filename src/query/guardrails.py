"""Question gate: PII, advice, performance, out-of-scope, then intent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

SEBI_LINK = "https://investor.sebi.gov.in/"
AMFI_LINK = "https://www.amfiindia.com/investor"
FACTSHEET_LINK = "https://www.hdfcfund.com/mutual-funds/factsheets"

FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("statement", re.compile(r"capital\s*gain|statement|tax\s*proof|\b80\s*c\b|download", re.I)),
    ("expense_ratio", re.compile(r"expense\s*ratio|\bter\b|total\s+expense", re.I)),
    ("exit_load", re.compile(r"exit\s*load", re.I)),
    ("lock_in", re.compile(r"lock[\s-]?in", re.I)),
    ("min_sip", re.compile(r"min(?:imum)?[\s.]*(?:sip|investment)|sip\s+amount", re.I)),
    (
        "riskometer",
        re.compile(
            r"riskometer|risk\s+level|rated\b.{0,25}\brisk\b|"
            r"\b(?:very\s+)?(?:high|moderate|low)\s+risk\b",
            re.I,
        ),
    ),
    ("benchmark", re.compile(r"benchmark|track(?:s|ing)?\s+(?:the\s+)?index", re.I)),
]

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.I)),
    ("pan", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")),
    ("account", re.compile(r"\b(?:account|a/c|acct)\b[^0-9]{0,20}\d{9,18}\b", re.I)),
    ("otp", re.compile(r"\botp\b[^0-9]{0,12}\d{4,8}\b", re.I)),
]

ADVICE_PATTERNS = [
    re.compile(r"\bshould\s+(?:i|we)\b", re.I),
    re.compile(r"\b(?:buy|sell|hold|switch|redeem|exit\s+from)\b", re.I),
    re.compile(r"\b(?:recommend|suggest|advice|advise)\b", re.I),
    re.compile(r"\bportfolio\b|\ballocat(?:e|ion)\b", re.I),
    re.compile(r"\bwhich\b.{0,30}\b(?:better|best)\b|\bbest\s+fund\b|\bbetter\s+fund\b", re.I),
    re.compile(r"\binvest\s+in\b", re.I),
]

RETURNS_PATTERNS = [
    re.compile(r"\breturns?\b|\bcagr\b|\bxirr\b|\bannuali[sz]ed\b", re.I),
    re.compile(r"\bperformance\b|\boutperform\b|\bbeat\s+the\b|\bbeat\s+benchmark\b", re.I),
    re.compile(r"\bcompare\b.{0,30}\b(?:return|performance|fund)\b", re.I),
    re.compile(r"\bhow\s+much\b.{0,30}\b(?:earn|grow|made)\b", re.I),
]

OTHER_AMCS = [
    "sbi", "icici", "axis", "kotak", "nippon", "franklin", "dsp", "aditya birla",
    "mirae", "tata", "uti", "quant", "parag parikh", "motilal", "bandhan",
    "canara", "idfc", "hsbc", "invesco", "loomis", "principal", "sundaram",
    "baroda", "edelweiss", "mahindra", "navi", "samco", "whiteoak", "360 one",
]


@dataclass
class GuardrailResult:
    blocked: bool
    intent: str
    field: str | None = None
    pii: bool = False
    reason: str = ""
    message: str = ""
    url: str = ""
    detected: list[str] = dc_field(default_factory=list)


def detect_field(question: str) -> str | None:
    for name, pattern in FIELD_PATTERNS:
        if pattern.search(question or ""):
            return name
    return None


def _pii_labels(question: str) -> list[str]:
    return [label for label, pattern in PII_PATTERNS if pattern.search(question or "")]


def _matches(question: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(question or "") for pattern in patterns)


def check_question(question: str) -> GuardrailResult:
    question = question or ""
    pii = _pii_labels(question)
    if pii:
        return GuardrailResult(
            blocked=True,
            intent="pii",
            field=detect_field(question),
            pii=True,
            reason="pii_detected",
            message=(
                "I don't need personal identifiers (PAN, Aadhaar, account number, OTP, "
                "email or phone) for these FAQs, so I won't accept or store them. "
                f"Please ask a scheme-fact question or see {SEBI_LINK}."
            ),
            url=SEBI_LINK,
            detected=pii,
        )

    if _matches(question, ADVICE_PATTERNS):
        return GuardrailResult(
            blocked=True,
            intent="advice",
            field=detect_field(question),
            reason="investment_advice",
            message=(
                "I can only share publicly available scheme facts, not investment advice. "
                f"For investor education, see {SEBI_LINK}."
            ),
            url=SEBI_LINK,
        )

    if _matches(question, RETURNS_PATTERNS):
        return GuardrailResult(
            blocked=True,
            intent="returns",
            field=detect_field(question),
            reason="performance_claims",
            message=(
                "I can't compute or compare returns or performance. "
                f"Please use the official factsheet: {FACTSHEET_LINK}."
            ),
            url=FACTSHEET_LINK,
        )

    lowered = question.lower()
    other = next((amc for amc in OTHER_AMCS if re.search(rf"\b{re.escape(amc)}\b", lowered)), None)
    if other:
        return GuardrailResult(
            blocked=True,
            intent="out_of_scope",
            field=detect_field(question),
            reason=f"other_amc:{other}",
            message=(
                "This demo covers HDFC Mutual Fund and four listed schemes only. "
                f"For general investor education, see {AMFI_LINK}."
            ),
            url=AMFI_LINK,
        )

    field_name = detect_field(question)
    intent = "statement" if field_name == "statement" else "fact"
    return GuardrailResult(blocked=False, intent=intent, field=field_name)


def is_in_scope_field(field_name: str | None) -> bool:
    return field_name in {name for name, _ in FIELD_PATTERNS}
