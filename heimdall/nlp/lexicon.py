"""Shared regex lexicon for outrage scoring and theme clustering."""

from __future__ import annotations

import re

DEHUMANIZING = re.compile(
    r"\b(vermin|animals|subhuman|parasite|infest|exterminate|filth|scum|"
    r"plague|locusts|cockroaches|breed like|invaded us|do not belong|no rights|"
    r"replace us|great replacement|untermensch|deport them all)\b",
    re.I,
)
ANTI_AUTHORITY = re.compile(
    r"\b(deep state|tyrann|martial law|illegitimate|stolen election|"
    r"they control|shadow government|traitors in|america\s*first|#americafirst|"
    r"rigged election|banana republic|dictator|pedo cabal|globalist cabal|"
    r"uniparty|weaponized (doj|fbi|irs)|political persecution)\b",
    re.I,
)
RAGEBAIT_MARKERS = re.compile(
    r"(!{2,}|wake up|share before|they don't want you|mainstream media won't|"
    r"you won't believe|destroying our country|hate you|nodaca|no ?daca|"
    r"open your eyes|before they censor|share if you agree|retweet if|"
    r"the truth they hide|do your research|sheeple|wake up america)\b",
    re.I,
)
HIGH_CONFLICT = re.compile(
    r"\b(enemy|war on|fight back|blood|revolution|purge|eliminate|"
    r"don'?t test me|ignorant|civil war|second amendment|molon labe|"
    r"traitors|hang them|execute|overthrow|by any means)\b",
    re.I,
)
TOXIC_PROFANITY = re.compile(
    r"\b(cunt|bitch ass|f+u+c+k+|shit|asshole|motherfucker)\b",
    re.I,
)
STANDALONE_BITCH = re.compile(r"\bbitch\b", re.I)
AFFECTION = re.compile(
    r"\b(i love you|ily|ilysm|thank u|thank you|my fave|with my whole heart|"
    r"spreads love|❤|💕|proud of you|grateful for)\b",
    re.I,
)
NEGATIVE_LEXICON = re.compile(
    r"\b(hate|destroy|evil|corrupt|lie|fake|invad|deport|illegal|"
    r"traitor|disgusting|pathetic|scum|garbage human|worst president|"
    r"clown show|disaster|betray|sellout|grifter|predator|sickening)\b",
    re.I,
)
STANCE_POLARIZATION = re.compile(
    r"\b(#semst|lock her up|crooked|witch|benghazi|climate hoax|"
    r"fake news|illegitimate|tyrant|socialist|communist|radical left|"
    r"radical right|destroy (our|the) (country|nation)|america first|"
    r"maga|ultramaga|woke mob|antifa|blm rioters|stop the steal|"
    r"pro.?life|pro.?choice extremist)\b",
    re.I,
)
CONSPIRACY = re.compile(
    r"\b(false flag|crisis actor|plandemic|great reset|new world order|"
    r"chemtrails|microchip|bioweapon|population control|"
    r"they're coming for|agenda 2030|globalist agenda)\b",
    re.I,
)
THREAT_VIOLENCE = re.compile(
    r"\b(shoot them|bring guns|armed and ready|heads on pikes|"
    r"string them up|lynch|burn it down|firebomb|assassinate)\b",
    re.I,
)

LEXICON_PATTERNS: tuple[re.Pattern[str], ...] = (
    DEHUMANIZING,
    ANTI_AUTHORITY,
    RAGEBAIT_MARKERS,
    HIGH_CONFLICT,
    TOXIC_PROFANITY,
    STANCE_POLARIZATION,
    NEGATIVE_LEXICON,
    CONSPIRACY,
    THREAT_VIOLENCE,
)


def lexicon_hit_strength(text: str) -> float:
    """Fraction of lexicon families matched (0-1). Used to spot non-dictionary themes."""
    if not text:
        return 0.0
    hits = sum(1 for pattern in LEXICON_PATTERNS if pattern.search(text))
    if STANDALONE_BITCH.search(text) and not AFFECTION.search(text):
        hits += 1
    return min(1.0, hits / max(len(LEXICON_PATTERNS), 1))
