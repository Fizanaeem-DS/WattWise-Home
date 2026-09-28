"""Deterministic probability classifier used by Stage 5B."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


@dataclass
class LogisticClassifier:
    """L2-regularized logistic regression fitted by fixed Newton steps."""

    alpha: float = 1.0
    max_iterations: int = 50
    tolerance: float = 1e-10
    means: np.ndarray | None = None
    scales: np.ndarray | None = None
    coefficients: np.ndarray | None = None
    intercept: float = 0.0
    iterations_used: int = 0

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LogisticClassifier":
        positives = int(np.sum(y == 1.0))
        negatives = int(np.sum(y == 0.0))
        if positives == 0 or negatives == 0:
            raise ValueError("Classifier training requires both high and normal observations")
        self.means = np.mean(x, axis=0)
        self.scales = np.std(x, axis=0)
        self.scales[self.scales == 0] = 1.0
        design = np.column_stack([np.ones(len(x)), (x - self.means) / self.scales])
        sample_weight = np.ones(len(y), dtype=float)
        parameters = np.zeros(design.shape[1], dtype=float)
        penalty = np.eye(design.shape[1], dtype=float) * self.alpha
        penalty[0, 0] = 0.0
        for iteration in range(1, self.max_iterations + 1):
            probability = _sigmoid(design @ parameters)
            gradient = design.T @ (sample_weight * (probability - y)) + penalty @ parameters
            curvature = sample_weight * probability * (1.0 - probability)
            hessian = design.T @ (design * curvature[:, None]) + penalty
            step = np.linalg.solve(hessian, gradient)
            parameters -= step
            self.iterations_used = iteration
            if float(np.max(np.abs(step))) < self.tolerance:
                break
        self.intercept = float(parameters[0])
        self.coefficients = parameters[1:]
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self.means is None or self.scales is None or self.coefficients is None:
            raise RuntimeError("Classifier is not fitted")
        linear = self.intercept + ((x - self.means) / self.scales) @ self.coefficients
        return _sigmoid(linear)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "l2_logistic_regression",
            "alpha": self.alpha,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
            "means": self.means.tolist() if self.means is not None else None,
            "scales": self.scales.tolist() if self.scales is not None else None,
            "coefficients": self.coefficients.tolist() if self.coefficients is not None else None,
            "intercept": self.intercept,
            "iterations_used": self.iterations_used,
            "class_weight": "none",
        }

