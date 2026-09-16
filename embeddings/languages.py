
"""
Language registry and auto-detection utilities for Resolvix.

Provides metadata (ISO 639-1 code, English name, native name, flag emoji)
for the 50+ languages natively supported by the
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 model, along with
intelligent language detection.
"""

from __future__ import annotations

import re
from typing import Any

# Supported 50+ languages for paraphrase-multilingual-MiniLM-L12-v2
SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "flag": "🇮🇳"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "flag": "🇮🇳"},
    "es": {"name": "Spanish", "native": "Español", "flag": "🇪🇸"},
    "fr": {"name": "French", "native": "Français", "flag": "🇫🇷"},
    "de": {"name": "German", "native": "Deutsch", "flag": "🇩🇪"},
    "ja": {"name": "Japanese", "native": "日本語", "flag": "🇯🇵"},
    "zh": {"name": "Chinese", "native": "中文", "flag": "🇨🇳"},
    "ar": {"name": "Arabic", "native": "العربية", "flag": "🇸🇦"},
    "ru": {"name": "Russian", "native": "Русский", "flag": "🇷🇺"},
    "pt": {"name": "Portuguese", "native": "Português", "flag": "🇧🇷"},
    "it": {"name": "Italian", "native": "Italiano", "flag": "🇮🇹"},
    "nl": {"name": "Dutch", "native": "Nederlands", "flag": "🇳🇱"},
    "pl": {"name": "Polish", "native": "Polski", "flag": "🇵🇱"},
    "tr": {"name": "Turkish", "native": "Türkçe", "flag": "🇹🇷"},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "flag": "🇻🇳"},
    "ko": {"name": "Korean", "native": "한국어", "flag": "🇰🇷"},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "flag": "🇮🇩"},
    "cs": {"name": "Czech", "native": "Čeština", "flag": "🇨🇿"},
    "ro": {"name": "Romanian", "native": "Română", "flag": "🇷🇴"},
    "sv": {"name": "Swedish", "native": "Svenska", "flag": "🇸🇪"},
    "hu": {"name": "Hungarian", "native": "Magyar", "flag": "🇭🇺"},
    "uk": {"name": "Ukrainian", "native": "Українська", "flag": "🇺🇦"},
    "el": {"name": "Greek", "native": "Ελληνικά", "flag": "🇬🇷"},
    "da": {"name": "Danish", "native": "Dansk", "flag": "🇩🇰"},
    "fi": {"name": "Finnish", "native": "Suomi", "flag": "🇫🇮"},
    "no": {"name": "Norwegian", "native": "Norsk", "flag": "🇳🇴"},
    "th": {"name": "Thai", "native": "ไทย", "flag": "🇹🇭"},
    "bn": {"name": "Bengali", "native": "বাংলা", "flag": "🇮🇳"},
    "te": {"name": "Telugu", "native": "తెలుగు", "flag": "🇮🇳"},
    "mr": {"name": "Marathi", "native": "मराठी", "flag": "🇮🇳"},
    "ur": {"name": "Urdu", "native": "اردو", "flag": "🇵🇰"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "flag": "🇮🇳"},
    "fa": {"name": "Persian", "native": "فارسی", "flag": "🇮🇷"},
    "he": {"name": "Hebrew", "native": "עברית", "flag": "🇮🇱"},
    "sk": {"name": "Slovak", "native": "Slovenčina", "flag": "🇸🇰"},
    "bg": {"name": "Bulgarian", "native": "Български", "flag": "🇧🇬"},
    "hr": {"name": "Croatian", "native": "Hrvatski", "flag": "🇭🇷"},
    "sr": {"name": "Serbian", "native": "Српски", "flag": "🇷🇸"},
    "lt": {"name": "Lithuanian", "native": "Lietuvių", "flag": "🇱🇹"},
    "sl": {"name": "Slovenian", "native": "Slovenščina", "flag": "🇸🇮"},
    "et": {"name": "Estonian", "native": "Eesti", "flag": "🇪🇪"},
    "lv": {"name": "Latvian", "native": "Latviešu", "flag": "🇱🇻"},
    "sw": {"name": "Swahili", "native": "Kiswahili", "flag": "🇰🇪"},
    "ca": {"name": "Catalan", "native": "Català", "flag": "🇪🇸"},
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "flag": "🇲🇾"},
    "tl": {"name": "Tagalog", "native": "Tagalog", "flag": "🇵🇭"},
    "ka": {"name": "Georgian", "native": "ქართული", "flag": "🇬🇪"},
    "hy": {"name": "Armenian", "native": "Հայերեն", "flag": "🇦🇲"},
    "ne": {"name": "Nepali", "native": "नेपाली", "flag": "🇳🇵"},
}

# Unicode script ranges for instant script recognition
SCRIPT_PATTERNS = [
    (re.compile(r"[\u0900-\u097F]"), "hi"),  # Devanagari (Hindi / Marathi / Nepali)
    (re.compile(r"[\u0B80-\u0BFF]"), "ta"),  # Tamil
    (re.compile(r"[\u0C00-\u0C7F]"), "te"),  # Telugu
    (re.compile(r"[\u0980-\u09FF]"), "bn"),  # Bengali
    (re.compile(r"[\u0A80-\u0AFF]"), "gu"),  # Gujarati
    (re.compile(r"[\u0600-\u06FF]"), "ar"),  # Arabic / Urdu / Persian
    (re.compile(r"[\u0400-\u04FF]"), "ru"),  # Cyrillic (Russian, etc.)
    (re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]"), "ja"),  # Japanese / Kanji
    (re.compile(r"[\uAC00-\uD7AF]"), "ko"),  # Korean Hangul
    (re.compile(r"[\u0E00-\u0E7F]"), "th"),  # Thai
    (re.compile(r"[\u0590-\u05FF]"), "he"),  # Hebrew
    (re.compile(r"[\u0370-\u03FF]"), "el"),  # Greek
]


def detect_language(text: str) -> str:
    """Detect the ISO 639-1 language code for the given text.

    Uses a two-stage approach:
    1. Fast Unicode script inspection for non-Latin scripts (Devanagari, Tamil,
       Arabic, Cyrillic, CJK, etc.)
    2. Fallback to `langdetect` (if installed) for Latin-script languages (English,
       Spanish, French, German, etc.)
    3. Defaults to 'en' if undetectable.
    """
    if not text or not text.strip():
        return "en"

    clean_text = text.strip()

    # Step 1: Script check for distinctive non-Latin scripts
    for pattern, code in SCRIPT_PATTERNS:
        matches = pattern.findall(clean_text)
        if len(matches) >= 2:
            return code

    # Step 2: Try langdetect for Latin and other languages
    try:
        from langdetect import DetectorFactory, detect
        # Set seed for deterministic detection
        DetectorFactory.seed = 0
        detected = detect(clean_text)
        if detected.startswith("zh"):
            return "zh"
        if detected in SUPPORTED_LANGUAGES:
            return detected
    except Exception:
        pass

    return "en"


def get_language_display(code: str) -> str:
    """Return a formatted string like '🇬🇧 English (en)' for a language code."""
    code_lower = str(code).lower()
    info = SUPPORTED_LANGUAGES.get(code_lower)
    if info:
        return f"{info['flag']} {info['name']} ({code_lower})"
    return f"🌐 {code.upper()}"


def get_language_flag(code: str) -> str:
    """Return flag emoji for a language code."""
    info = SUPPORTED_LANGUAGES.get(str(code).lower())
    return info["flag"] if info else "🌐"


def get_language_name(code: str) -> str:
    """Return human readable English name for a language code."""
    info = SUPPORTED_LANGUAGES.get(str(code).lower())
    return info["name"] if info else code.upper()
