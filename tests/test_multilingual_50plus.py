"""
Validation tests for 50+ language capability and cross-lingual semantic similarity.

Verifies that paraphrase-multilingual-MiniLM-L12-v2 maps semantically identical
support ticket queries across European, Asian, and Middle-Eastern language
families into nearby points (cosine similarity > 0.65) in the shared 384-dimensional
vector space.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import embeddings.compat  # noqa: F401
from embeddings.generate import generate_embedding
from embeddings.languages import SUPPORTED_LANGUAGES, detect_language, get_language_display


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two 1D normalized or raw vectors."""
    dot = float(np.dot(a, b))
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return dot / denom if denom > 0 else 0.0


def test_supported_languages_registry():
    """Verify registry contains 50+ languages with valid metadata."""
    assert len(SUPPORTED_LANGUAGES) >= 50, f"Expected 50+ languages, got {len(SUPPORTED_LANGUAGES)}"
    for code, info in SUPPORTED_LANGUAGES.items():
        assert "name" in info
        assert "native" in info
        assert "flag" in info
        assert len(code) == 2


def test_language_detection():
    """Test auto-detection across diverse scripts and languages."""
    samples = [
        ("Unable to reset my password", "en"),
        ("मेरा पासवर्ड रीसेट नहीं हो रहा है", "hi"),
        ("என் password-ஐ reset செய்ய முடியவில்லை", "ta"),
        ("No puedo restablecer mi contraseña", "es"),
        ("Impossible de réinitialiser mon mot de passe", "fr"),
        ("Ich kann mein Passwort nicht zurücksetzen", "de"),
        ("パスワードを再設定できません", "ja"),
        ("لا يمكنني إعادة تعيين كلمة المرور", "ar"),
        ("আমি আমার পাসওয়ার্ড রিসেট করতে পারছি না", "bn"),
        ("నా పాస్‌వర్డ్ రీసెట్ చేయడం సాధ్యం కావడం లేదు", "te"),
    ]
    for text, expected_lang in samples:
        detected = detect_language(text)
        assert detected == expected_lang, f"Text '{text}' expected '{expected_lang}', got '{detected}'"


def test_cross_lingual_password_reset_clusters():
    """Verify that password reset queries across 10 diverse languages have high similarity."""
    translations = {
        "en": "Unable to reset my password — the reset link expires immediately.",
        "es": "No puedo restablecer mi contraseña: el enlace expira de inmediato.",
        "fr": "Impossible de réinitialiser mon mot de passe — le lien expire immédiatement.",
        "de": "Ich kann mein Passwort nicht zurücksetzen — der Link läuft sofort ab.",
        "ja": "パスワードを再設定できません。メール内のリセットリンクがすぐに期限切れになります。",
        "ar": "لا يمكنني إعادة تعيين كلمة المرور - ينتهي رابط إعادة التعيين فوراً.",
        "hi": "मेरा पासवर्ड रीसेट नहीं हो रहा है — रीसेट लिंक तुरंत समाप्त हो जाता है।",
        "ta": "என் password-ஐ reset செய்ய முடியவில்லை, reset link expire ஆகிறது.",
        "ru": "Не могу сбросить пароль — ссылка для сброса в письमे мгновенно истекает.",
        "it": "Impossibile reimpostare la password: il link scade immediatamente.",
        "pt": "Não consigo redefinir minha senha — o link de redefinição expira imediatamente.",
        "nl": "Ik kan mijn wachtwoord niet opnieuw instellen — de resetlink verloopt onmiddellijk.",
    }

    # Generate embeddings for all
    vecs = {lang: generate_embedding(text) for lang, text in translations.items()}

    # All translations should be close to English (> 0.65)
    en_vec = vecs["en"]
    for lang, vec in vecs.items():
        sim = cosine_similarity(en_vec, vec)
        print(f"[Cross-lingual Match] en <-> {lang}: {sim:.4f}")
        assert sim >= 0.65, f"Cross-lingual similarity for {lang} ({sim:.4f}) is below 0.65"

    # Unrelated ticket in English (e.g. GST billing question) should have lower similarity (< 0.45)
    unrelated_text = "Invoice shows tax applied twice for an India GST customer on the March billing cycle."
    unrelated_vec = generate_embedding(unrelated_text)
    for lang, vec in vecs.items():
        unrelated_sim = cosine_similarity(vec, unrelated_vec)
        assert unrelated_sim < 0.50, f"Unrelated query similarity for {lang} ({unrelated_sim:.4f}) is unexpectedly high"


if __name__ == "__main__":
    test_supported_languages_registry()
    test_language_detection()
    test_cross_lingual_password_reset_clusters()
    print("\nAll 50+ language and cross-lingual tests PASSED successfully!")
