"""Small deterministic NumPy regressors used by Stage 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _leaf(value: float) -> dict[str, Any]:
    return {"leaf": float(value)}


def _predict_tree(node: dict[str, Any], row: np.ndarray) -> float:
    current = node
    while "leaf" not in current:
        current = current["left"] if row[current["feature"]] <= current["threshold"] else current["right"]
    return float(current["leaf"])


def _fit_tree(
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    depth: int,
    max_depth: int,
    min_samples_leaf: int,
) -> dict[str, Any]:
    if depth >= max_depth or len(indices) < 2 * min_samples_leaf:
        return _leaf(float(np.mean(y[indices])))
    best: tuple[float, int, float, np.ndarray, np.ndarray] | None = None
    for feature in range(x.shape[1]):
        order = indices[np.argsort(x[indices, feature], kind="mergesort")]
        values = x[order, feature]
        targets = y[order]
        cumulative = np.cumsum(targets)
        cumulative_sq = np.cumsum(targets * targets)
        total_sum = cumulative[-1]
        total_sq = cumulative_sq[-1]
        for split in range(min_samples_leaf, len(order) - min_samples_leaf + 1):
            if split >= len(order) or values[split - 1] == values[split]:
                continue
            left_n = split
            right_n = len(order) - split
            left_sum = cumulative[split - 1]
            left_sq = cumulative_sq[split - 1]
            right_sum = total_sum - left_sum
            right_sq = total_sq - left_sq
            loss = (left_sq - left_sum * left_sum / left_n) + (right_sq - right_sum * right_sum / right_n)
            threshold = float((values[split - 1] + values[split]) / 2)
            candidate = (float(loss), feature, threshold, order[:split], order[split:])
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        return _leaf(float(np.mean(y[indices])))
    _, feature, threshold, left_indices, right_indices = best
    return {
        "feature": int(feature),
        "threshold": threshold,
        "left": _fit_tree(x, y, left_indices, depth + 1, max_depth, min_samples_leaf),
        "right": _fit_tree(x, y, right_indices, depth + 1, max_depth, min_samples_leaf),
    }


@dataclass
class GradientBoostedRegressor:
    n_estimators: int = 40
    learning_rate: float = 0.05
    max_depth: int = 2
    min_samples_leaf: int = 20
    base_value: float = 0.0
    trees: list[dict[str, Any]] | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "GradientBoostedRegressor":
        self.base_value = float(np.mean(y))
        self.trees = []
        predictions = np.full(len(y), self.base_value, dtype=float)
        indices = np.arange(len(y))
        for _ in range(self.n_estimators):
            residual = y - predictions
            tree = _fit_tree(x, residual, indices, 0, self.max_depth, self.min_samples_leaf)
            update = np.array([_predict_tree(tree, row) for row in x])
            predictions += self.learning_rate * update
            self.trees.append(tree)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.trees is None:
            raise RuntimeError("Model is not fitted")
        predictions = np.full(len(x), self.base_value, dtype=float)
        for tree in self.trees:
            predictions += self.learning_rate * np.array([_predict_tree(tree, row) for row in x])
        return predictions

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "gradient_boosted_regression_trees",
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "base_value": self.base_value,
            "trees": self.trees,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GradientBoostedRegressor":
        return cls(
            n_estimators=payload["n_estimators"],
            learning_rate=payload["learning_rate"],
            max_depth=payload["max_depth"],
            min_samples_leaf=payload["min_samples_leaf"],
            base_value=payload["base_value"],
            trees=payload["trees"],
        )


@dataclass
class RidgeRegressor:
    alpha: float = 10.0
    means: np.ndarray | None = None
    scales: np.ndarray | None = None
    coefficients: np.ndarray | None = None
    intercept: float = 0.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> "RidgeRegressor":
        self.means = np.mean(x, axis=0)
        self.scales = np.std(x, axis=0)
        self.scales[self.scales == 0] = 1.0
        standardized = (x - self.means) / self.scales
        design = np.column_stack([np.ones(len(x)), standardized])
        penalty = np.eye(design.shape[1]) * self.alpha
        penalty[0, 0] = 0.0
        solution = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        self.intercept = float(solution[0])
        self.coefficients = solution[1:]
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.means is None or self.scales is None or self.coefficients is None:
            raise RuntimeError("Model is not fitted")
        return self.intercept + ((x - self.means) / self.scales) @ self.coefficients

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "ridge_regression",
            "alpha": self.alpha,
            "means": self.means.tolist() if self.means is not None else None,
            "scales": self.scales.tolist() if self.scales is not None else None,
            "coefficients": self.coefficients.tolist() if self.coefficients is not None else None,
            "intercept": self.intercept,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RidgeRegressor":
        return cls(
            alpha=payload["alpha"],
            means=np.array(payload["means"], dtype=float),
            scales=np.array(payload["scales"], dtype=float),
            coefficients=np.array(payload["coefficients"], dtype=float),
            intercept=payload["intercept"],
        )


def model_from_dict(payload: dict[str, Any]):
    if payload["model_type"] == "gradient_boosted_regression_trees":
        return GradientBoostedRegressor.from_dict(payload)
    if payload["model_type"] == "ridge_regression":
        return RidgeRegressor.from_dict(payload)
    raise ValueError(f"Unsupported model type {payload['model_type']}")
