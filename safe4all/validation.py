"""Product-versus-station statistics for transparent workshop validation."""

from __future__ import annotations

from math import isfinite, sqrt


def rainfall_metrics(observed, estimated) -> dict[str, float]:
    """Return paired rainfall validation metrics, excluding missing pairs."""
    pairs = [(float(obs), float(est)) for obs, est in zip(observed, estimated)
             if isfinite(float(obs)) and isfinite(float(est))]
    if len(pairs) < 3:
        raise ValueError("At least three paired observations are required.")
    errors = [est - obs for obs, est in pairs]
    observations = [obs for obs, _ in pairs]
    estimates = [est for _, est in pairs]
    observed_mean = sum(observations) / len(observations)
    estimated_mean = sum(estimates) / len(estimates)
    numerator = sum((obs - observed_mean) * (est - estimated_mean) for obs, est in pairs)
    denominator = sqrt(sum((obs - observed_mean) ** 2 for obs in observations) *
                       sum((est - estimated_mean) ** 2 for est in estimates))
    return {
        "n": float(len(pairs)),
        "bias_mm": sum(errors) / len(errors),
        "mae_mm": sum(abs(error) for error in errors) / len(errors),
        "rmse_mm": sqrt(sum(error ** 2 for error in errors) / len(errors)),
        "correlation": numerator / denominator if denominator else float("nan"),
    }
