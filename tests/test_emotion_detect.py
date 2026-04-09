"""Tests for the auto emotion detection module."""

from __future__ import annotations

import pytest

from cogmem.utils.emotion_detect import detect_emotion


class TestDetectPain:
    def test_strong_pain_signal(self):
        emotion, intensity = detect_emotion("Production crashed and we lost data")
        assert emotion == "pain"
        assert intensity >= 0.7


class TestDetectFrustration:
    def test_frustration_signal(self):
        emotion, _intensity = detect_emotion("This took forever to debug")
        assert emotion == "frustration"


class TestDetectRelief:
    def test_relief_signal(self):
        emotion, _intensity = detect_emotion("Finally fixed the auth bug")
        assert emotion == "relief"


class TestDetectTrust:
    def test_trust_signal(self):
        emotion, _intensity = detect_emotion("This module is solid and well-tested")
        assert emotion == "trust"


class TestDetectNeutral:
    def test_neutral_signal(self):
        emotion, _intensity = detect_emotion("Updated the readme")
        assert emotion == "neutral"


class TestNegation:
    def test_negation_flips_pain(self):
        emotion, _intensity = detect_emotion("No bugs found, everything working")
        assert emotion != "pain"


class TestFileContextBias:
    def test_context_biases_toward_existing_emotion(self):
        # Neutral-ish text mentioning a file component
        file_context = {"src/auth/login.py": "pain"}
        emotion, _intensity = detect_emotion(
            "Made changes to the auth login module",
            file_context=file_context,
        )
        assert emotion == "pain"


class TestIntensityScaling:
    def test_stronger_signals_higher_intensity(self):
        _, weak_intensity = detect_emotion("There was an error")
        _, strong_intensity = detect_emotion(
            "Production crashed with a deadlock, data lost and corrupted"
        )
        assert strong_intensity > weak_intensity
