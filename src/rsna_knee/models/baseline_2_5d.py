"""Lightweight 2.5D baseline model using only numpy (no torch dependency).

This is a reference implementation for smoke testing the training loop and
OOF writer. It is not intended for competition submission; a real encoder will
replace it after data access opens.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


class Baseline2_5D:
    """Per-study mean-pool over slices, then a single linear layer per target."""

    def __init__(
        self,
        *,
        n_targets: int = 12,
        seed: int = 42,
    ) -> None:
        if n_targets < 1:
            raise ValueError("n_targets must be >= 1")
        self.n_targets = n_targets
        rng = np.random.default_rng(seed)
        # Weight shape: [features, targets]; features = pooled slice statistics.
        self.weights: npt.NDArray[np.float64] = rng.normal(0.0, 0.01, size=(4, n_targets))
        self.bias: npt.NDArray[np.float64] = np.zeros(n_targets)

    def _pool(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Pool slice tensor to per-study features: [mean, std, min, max]."""
        # Pool over all non-batch dims: [batch, C, H, W] -> [batch].
        return np.stack(
            [
                x.mean(axis=(1, 2, 3)),
                x.std(axis=(1, 2, 3)),
                x.min(axis=(1, 2, 3)),
                x.max(axis=(1, 2, 3)),
            ],
            axis=1,
        )

    def forward(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Forward pass: input shape [batch, channels, height, width] or [batch, H, W]."""
        if x.ndim == 3:
            x = x[:, np.newaxis, :, :]
        pooled = self._pool(x)
        logits = pooled @ self.weights + self.bias
        return 1.0 / (1.0 + np.exp(-logits))  # sigmoid for probability output
