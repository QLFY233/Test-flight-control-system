"""FFT analysis tool — computes spectrum of a time series."""

from __future__ import annotations

import math
from typing import Any


class FFTTool:
    """Simple FFT analysis using basic DFT (no numpy dependency required).

    For production, swap to numpy.fft for performance.
    """

    def analyze(self, data: list[float], params: dict) -> dict:
        """Compute frequency spectrum of data.

        Args:
            data: List of float values (time series).
            params: { "sampling_rate": float (Hz, default 10.0) }

        Returns:
            dict with frequencies, magnitudes, dominant_freq, etc.
        """
        if not data:
            return {"error": "no data provided"}

        sampling_rate = params.get("sampling_rate", 10.0)
        n = len(data)

        # Simple DFT magnitudes using numpy if available, else pure Python
        try:
            import numpy as np
            fft = np.fft.rfft(data)
            magnitudes = np.abs(fft).tolist()
            freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate).tolist()
        except ImportError:
            freqs, magnitudes = self._simple_dft(data, sampling_rate)

        # Find dominant frequency
        if magnitudes:
            max_idx = max(range(len(magnitudes)), key=lambda i: magnitudes[i])
            dominant_freq = freqs[max_idx] if max_idx < len(freqs) else 0
            dominant_mag = magnitudes[max_idx]
        else:
            dominant_freq = 0
            dominant_mag = 0

        # Top 5 peaks
        peaks = sorted(
            zip(freqs, magnitudes), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "n_samples": n,
            "sampling_rate": sampling_rate,
            "frequencies": freqs[:50],  # limit for JSON size
            "magnitudes": [round(m, 4) for m in magnitudes[:50]],
            "dominant_frequency": round(dominant_freq, 4),
            "dominant_magnitude": round(dominant_mag, 4),
            "top_peaks": [
                {"frequency": round(f, 4), "magnitude": round(m, 4)}
                for f, m in peaks
            ],
        }

    def _simple_dft(self, data: list[float], sampling_rate: float) -> tuple[list[float], list[float]]:
        """Pure-Python DFT (slow, for fallback only)."""
        n = len(data)
        k_limit = n // 2 + 1
        freqs = [i * sampling_rate / n for i in range(k_limit)]
        magnitudes = []
        for k in range(k_limit):
            real = 0.0
            imag = 0.0
            for t in range(n):
                angle = -2.0 * math.pi * k * t / n
                real += data[t] * math.cos(angle)
                imag += data[t] * math.sin(angle)
            magnitudes.append(math.sqrt(real * real + imag * imag))
        return freqs, magnitudes
