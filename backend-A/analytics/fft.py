"""
FFT 频谱分析工具 — AnalyticsTool 接口实现。
支持幅值谱/功率谱/相位谱, 可经总线调度。
"""
import math
import logging

logger = logging.getLogger(__name__)

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


class FFTAnalyzer:
    """FFT 分析器 — 实现 AnalyticsTool 接口。"""

    name = "fft"

    def handle(self, tool: str, args: dict) -> dict:
        if tool == "fft":
            return self.run(
                args.get("data", []),
                args.get("options", {}),
            )
        return {"status": "error", "reason": f"unknown tool: {tool}"}

    def run(self, data: list, options: dict | None = None) -> dict:
        """对时序数据执行 FFT 分析。

        data: 实数序列
        options: {sample_rate?: float, type?: "amplitude"|"power"|"phase"}
        """
        if not data:
            return {"status": "error", "reason": "empty data"}

        opts = options or {}
        sample_rate = opts.get("sample_rate", 10.0)  # 默认 10Hz
        spectrum_type = opts.get("type", "amplitude")

        n = len(data)

        if _HAS_NUMPY:
            result = self._fft_numpy(data, n, sample_rate, spectrum_type)
        else:
            result = self._fft_dft(data, n, sample_rate, spectrum_type)

        return {"status": "ok", "spectrum": result, "n_samples": n, "sample_rate": sample_rate}

    def _fft_numpy(self, data: list, n: int, sr: float, stype: str) -> dict:
        """NumPy FFT 实现 (快速)。"""
        arr = np.array(data, dtype=np.float64)
        spectrum = np.fft.rfft(arr)
        freqs = np.fft.rfftfreq(n, d=1.0 / sr)

        if stype == "power":
            mag = (np.abs(spectrum) ** 2) / n
        elif stype == "phase":
            return {
                "frequencies": freqs.tolist()[:50],
                "phase": np.angle(spectrum).tolist()[:50],
            }
        else:  # amplitude
            mag = np.abs(spectrum) / n

        # 返回前 50 个频率分量 (去直流)
        return {
            "frequencies": freqs.tolist()[1:51],
            "magnitudes": mag.tolist()[1:51],
            "dominant_freq": float(freqs[1 + int(np.argmax(mag[1:]))]),
            "dominant_magnitude": float(np.max(mag[1:])),
        }

    def _fft_dft(self, data: list, n: int, sr: float, stype: str) -> dict:
        """纯 Python DFT 实现 (慢, 作为无 NumPy 时的 fallback)。"""
        half = n // 2 + 1
        freqs = [k * sr / n for k in range(min(50, half))]
        magnitudes = []

        for k in range(1, min(51, half)):  # skip DC
            real = 0.0
            imag = 0.0
            for i in range(n):
                angle = -2.0 * math.pi * k * i / n
                real += data[i] * math.cos(angle)
                imag += data[i] * math.sin(angle)
            mag = math.sqrt(real * real + imag * imag) / n
            magnitudes.append(mag)

        max_idx = magnitudes.index(max(magnitudes)) if magnitudes else 0
        return {
            "frequencies": freqs[1:51],
            "magnitudes": magnitudes,
            "dominant_freq": freqs[1 + max_idx] if max_idx < len(freqs) - 1 else 0,
            "dominant_magnitude": magnitudes[max_idx] if magnitudes else 0,
        }
