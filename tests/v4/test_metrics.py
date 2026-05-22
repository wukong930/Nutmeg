"""Tests for nutmeg.v4.eval.metrics."""
import numpy as np
import pytest

from nutmeg.v4.eval.metrics import (
    brier, ece, encode_labels, hit_rate, log_loss, summary,
)


class TestEncodeLabels:
    def test_string_labels(self):
        assert (encode_labels(["H", "D", "A"]) == np.array([0, 1, 2])).all()

    def test_int_labels(self):
        assert (encode_labels([0, 1, 2]) == np.array([0, 1, 2])).all()


class TestLogLoss:
    def test_perfect_prediction(self):
        probs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        y = ["H", "D", "A"]
        # Clipped to EPS, so not exactly 0 — but should be tiny
        ll = log_loss(probs, y)
        assert ll < 1e-6

    def test_uniform_gives_log_three(self):
        probs = np.full((10, 3), 1/3)
        y = ["H"] * 10
        assert log_loss(probs, y) == pytest.approx(np.log(3), rel=1e-6)

    def test_wrong_class_penalized(self):
        probs = np.array([[0.01, 0.49, 0.50]])
        y = ["H"]
        ll = log_loss(probs, y)
        assert ll > 4  # confident wrong is very expensive


class TestBrier:
    def test_perfect_zero(self):
        probs = np.array([[1.0, 0.0, 0.0]])
        assert brier(probs, ["H"]) == pytest.approx(0.0, abs=1e-9)

    def test_uniform(self):
        probs = np.full((1, 3), 1/3)
        # (1/3-1)^2 + (1/3)^2 + (1/3)^2 = 4/9 + 1/9 + 1/9 = 6/9 = 2/3
        assert brier(probs, ["H"]) == pytest.approx(2/3, abs=1e-9)


class TestHitRate:
    def test_argmax_correct(self):
        probs = np.array([[0.6, 0.3, 0.1], [0.1, 0.7, 0.2], [0.2, 0.3, 0.5]])
        y = ["H", "D", "A"]
        assert hit_rate(probs, y) == 1.0

    def test_argmax_wrong(self):
        probs = np.array([[0.6, 0.3, 0.1]])
        y = ["A"]
        assert hit_rate(probs, y) == 0.0


class TestECE:
    def test_perfectly_calibrated_is_zero(self):
        # 100 predictions all at 0.8 confidence, 80% correct → ECE = 0
        n = 100
        probs = np.full((n, 3), 0.1)
        probs[:, 0] = 0.8
        y = ["H"] * 80 + ["A"] * 20
        # All argmax = H. Confidence = 0.8. Accuracy = 0.8. ECE = 0.
        assert ece(probs, y) < 0.01


class TestSummary:
    def test_returns_all_metrics(self):
        probs = np.array([[0.5, 0.3, 0.2], [0.2, 0.5, 0.3]])
        y = ["H", "D"]
        s = summary(probs, y)
        assert set(s.keys()) == {"n", "log_loss", "brier", "hit_rate", "ece"}
        assert s["n"] == 2
