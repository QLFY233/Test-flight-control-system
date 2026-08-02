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

        # N12: n<2 提前返回 — numpy rfft/argmax 与 DFT 下标均会在 1 样本时崩溃
        if n < 2:
            return {
                "status": "ok",
                "spectrum": {
                    "frequencies": [],
                    "magnitudes": [],
                    "dominant_freq": 0.0,
                    "dominant_magnitude": 0.0,
                },
                "n_samples": n,
                "sample_rate": sample_rate,
            }

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
        # N12: frequencies 与 magnitudes 同源同长 (原实现 off-by-one:
        # dominant_freq 取 freqs[1+max_idx] 与 magnitudes 下标错位)
        k_max = min(51, n // 2 + 1)
        freqs = [k * sr / n for k in range(1, k_max)]  # 去 DC
        magnitudes = []

        for k in range(1, k_max):
            real = 0.0
            imag = 0.0
            for i in range(n):
                angle = -2.0 * math.pi * k * i / n
                real += data[i] * math.cos(angle)
                imag += data[i] * math.sin(angle)
            mag = math.sqrt(real * real + imag * imag) / n
            magnitudes.append(mag)

        if magnitudes:
            max_idx = magnitudes.index(max(magnitudes))
            dominant_freq = freqs[max_idx]
            dominant_magnitude = magnitudes[max_idx]
        else:
            dominant_freq = 0.0
            dominant_magnitude = 0.0
        return {
            "frequencies": freqs,
            "magnitudes": magnitudes,
            "dominant_freq": dominant_freq,
            "dominant_magnitude": dominant_magnitude,
        }
