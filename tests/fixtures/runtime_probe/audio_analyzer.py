# Derived from s007 audio_analyzer.py.
# SHA256: a8337f5b446f40659fdd43c0f5a28d1921aaff381c93eb010e4d77937ff06e3b.
"""
audio_analyzer.py
Strict, standalone sample-spec-aware audio PCM analyzer for CBrowser v2 isolation probe.
Performs:
- Raw S16LE stereo PCM decoding
- Non-zero byte and RMS silence validation
- Dual-method frequency estimation:
  1) Hysteresis-filtered Zero-Crossing Rate (ZCR)
  2) Direct Fourier Peak / Autocorrelation pitch extraction
- Strict 1% pitch tolerance verification (rejecting historical 8.2% pitch mismatch)
- Negative frequency / rate-mismatch rejection mode
- Cross-profile tone crosstalk analysis
"""

import argparse
import math
import os
import struct


def extract_channel_samples(
    data: bytes, channel: int = 0, sample_width: int = 2, num_channels: int = 2
):
    """Extract signed 16-bit PCM samples from interleaved multi-channel raw bytes."""
    frame_size = sample_width * num_channels
    num_frames = len(data) // frame_size
    samples = []
    offset = channel * sample_width
    for i in range(num_frames):
        val = struct.unpack_from("<h", data, i * frame_size + offset)[0]
        samples.append(val)
    return samples


def compute_rms(samples):
    """Compute Root-Mean-Square (RMS) amplitude of audio samples."""
    if not samples:
        return 0.0
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / len(samples))


def estimate_frequency_autocorr(
    samples, sample_rate: int, min_freq: float = 100.0, max_freq: float = 2000.0
):
    """
    Estimate dominant fundamental frequency via normalized autocorrelation
    with parabolic peak refinement.
    """
    if len(samples) < 1024:
        raise ValueError(
            f"Sample slice too short for autocorrelation: {len(samples)} samples"
        )

    # Use central analysis window of up to 4096 samples
    n = min(len(samples), 4096)
    start = (len(samples) - n) // 2
    w = samples[start : start + n]

    min_lag = int(sample_rate / max_freq)
    max_lag = int(sample_rate / min_freq)

    # Energy at lag 0
    energy_0 = sum(x * x for x in w)
    if energy_0 == 0:
        return 0.0

    corrs = []
    lags = list(range(min_lag, max_lag + 1))
    for lag in lags:
        c = 0
        for i in range(n - lag):
            c += w[i] * w[i + lag]
        corrs.append(c)

    # Find peak in correlation curve
    peak_idx = -1
    peak_val = -1e12
    for i in range(1, len(corrs) - 1):
        if corrs[i] > corrs[i - 1] and corrs[i] > corrs[i + 1] and corrs[i] > peak_val:
            peak_val = corrs[i]
            peak_idx = i

    if peak_idx <= 0:
        # Fallback to absolute max
        peak_idx = max(range(len(corrs)), key=lambda i: corrs[i])

    actual_lag = lags[peak_idx]

    # Parabolic interpolation for sub-sample accuracy
    if 0 < peak_idx < len(corrs) - 1:
        alpha = corrs[peak_idx - 1]
        beta = corrs[peak_idx]
        gamma = corrs[peak_idx + 1]
        denom = 2 * (alpha - 2 * beta + gamma)
        if denom != 0:
            delta = (alpha - gamma) / denom
            refined_lag = actual_lag + delta
        else:
            refined_lag = float(actual_lag)
    else:
        refined_lag = float(actual_lag)

    return sample_rate / refined_lag


def estimate_frequency_zcr(samples, sample_rate: int, hysteresis: int = 500):
    """
    Estimate fundamental frequency via hysteresis-filtered zero crossing count.
    Hysteresis prevents low-level quantization noise from creating false crossings.
    """
    state = 0  # 1 for positive, -1 for negative
    crossings = 0
    first_idx = -1
    last_idx = -1

    for idx, s in enumerate(samples):
        if s > hysteresis and state != 1:
            state = 1
            crossings += 1
            if first_idx < 0:
                first_idx = idx
            last_idx = idx
        elif s < -hysteresis and state != -1:
            state = -1
            crossings += 1
            if first_idx < 0:
                first_idx = idx
            last_idx = idx

    if crossings < 4 or first_idx == last_idx:
        return 0.0

    duration = (last_idx - first_idx) / sample_rate
    # crossings count transitions; 2 transitions per sine cycle
    est_freq = ((crossings - 1) / 2.0) / duration
    return est_freq


def compute_band_energy(
    samples, sample_rate: int, center_freq: float, bw_ratio: float = 0.05
):
    """Measure energy at the target frequency using Goertzel."""
    k = center_freq / sample_rate
    omega = 2.0 * math.pi * k
    coeff = 2.0 * math.cos(omega)
    q0 = q1 = q2 = 0.0

    n = min(len(samples), 4096)
    for i in range(n):
        q0 = coeff * q1 - q2 + samples[i]
        q2 = q1
        q1 = q0

    power = q1 * q1 + q2 * q2 - q1 * q2 * coeff
    return max(0.0, power)


def analyze_pcm(
    file_path: str,
    expected_freq: float,
    sample_rate: int = 48000,
    tolerance: float = 0.01,
    expect_fail: bool = False,
    crosstalk_freq: float | None = None,
):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    size = os.path.getsize(file_path)
    print(
        f"[audio_analyzer] File {file_path}: size={size} bytes, nominal"
        f" rate={sample_rate}Hz"
    )
    assert size >= 8000, f"File too small ({size} bytes)"

    with open(file_path, "rb") as f:
        data = f.read()

    non_zero = sum(1 for b in data if b != 0)
    ratio = (non_zero / size) * 100.0
    print(f"[audio_analyzer] Non-zero bytes: {non_zero}/{size} ({ratio:.1f}%)")
    assert ratio > 50.0, f"Audio is mostly silent ({ratio:.1f}% non-zero)"

    # Channel 0 samples
    samples = extract_channel_samples(data, channel=0, sample_width=2, num_channels=2)
    rms = compute_rms(samples)
    print(
        f"[audio_analyzer] Total frames: {len(samples)}, RMS amplitude: {rms:.1f} /"
        f" 32768 ({rms / 32768 * 100:.1f}% full-scale)"
    )
    assert rms > 500.0, f"Audio RMS energy too low ({rms:.1f}), signal absent"

    # Active slice (trim silence below 10% RMS)
    thresh = rms * 0.10
    first_active = next((i for i, s in enumerate(samples) if abs(s) > thresh), 0)
    last_active = len(samples) - next(
        (i for i, s in enumerate(reversed(samples)) if abs(s) > thresh), 0
    )
    active_samples = samples[first_active:last_active]
    print(
        f"[audio_analyzer] Active window: {len(active_samples)}/{len(samples)} samples"
        f" ({len(active_samples) / sample_rate:.3f}s)"
    )
    assert len(active_samples) >= int(sample_rate * 0.1), (
        f"Active audio window too short ({len(active_samples)} samples)"
    )

    # Frequency estimation
    freq_autocorr = estimate_frequency_autocorr(
        active_samples, sample_rate, min_freq=50.0, max_freq=3000.0
    )
    freq_zcr = estimate_frequency_zcr(
        active_samples, sample_rate, hysteresis=int(rms * 0.15)
    )

    print(f"[audio_analyzer] Measured Autocorrelation Freq : {freq_autocorr:.2f} Hz")
    print(f"[audio_analyzer] Measured Zero-Crossing Freq    : {freq_zcr:.2f} Hz")

    # Use refined autocorrelation as primary, cross-validate with ZCR
    est_freq = freq_autocorr
    zcr_diff_pct = (
        abs(freq_autocorr - freq_zcr) / freq_autocorr * 100.0
        if freq_autocorr > 0
        else 999.0
    )
    print(f"[audio_analyzer] ZCR vs Autocorr divergence   : {zcr_diff_pct:.2f}%")
    assert zcr_diff_pct < 5.0, (
        f"Inconsistent frequency measurements: Autocorr={freq_autocorr:.2f}Hz,"
        f" ZCR={freq_zcr:.2f}Hz"
    )

    # Check against expected frequency with strict tolerance
    err_hz = abs(est_freq - expected_freq)
    err_pct = (err_hz / expected_freq) * 100.0
    max_err_hz = expected_freq * tolerance

    print(
        f"[audio_analyzer] Expected Freq: {expected_freq:.1f} Hz, Tolerance:"
        f" {tolerance * 100:.1f}% (max err: {max_err_hz:.2f} Hz)"
    )
    print(f"[audio_analyzer] Frequency Error: {err_hz:.2f} Hz ({err_pct:.3f}%)")

    # Check crosstalk if specified
    if crosstalk_freq:
        e_target = compute_band_energy(active_samples, sample_rate, expected_freq)
        e_crosstalk = compute_band_energy(active_samples, sample_rate, crosstalk_freq)
        crosstalk_ratio = (e_crosstalk / e_target) if e_target > 0 else 0.0
        print(
            f"[audio_analyzer] Crosstalk check @ {crosstalk_freq}Hz:"
            f" ratio={crosstalk_ratio:.6f}"
        )
        assert crosstalk_ratio < 0.01, (
            f"Significant tone crosstalk detected at {crosstalk_freq}Hz:"
            f" ratio={crosstalk_ratio:.4f}"
        )

    if expect_fail:
        # Negative test mode: must NOT match expected frequency
        if err_pct <= tolerance * 100.0:
            raise AssertionError(
                f"Negative test failed: Frequency {est_freq:.2f}Hz matched unexpected"
                f" {expected_freq}Hz within {tolerance * 100}%!"
            )
        print(
            f"[audio_analyzer] NEGATIVE CHECK PASS: Frequency {est_freq:.2f}Hz"
            f" correctly REJECTED against {expected_freq}Hz ({err_pct:.2f}% error >"
            f" {tolerance * 100}%)."
        )
        return {
            "status": "NEGATIVE_REJECT_PASS",
            "est_freq": est_freq,
            "expected_freq": expected_freq,
            "err_pct": err_pct,
        }
    else:
        # Positive test mode: must match expected frequency strictly within tolerance
        assert err_pct <= tolerance * 100.0, (
            f"Frequency mismatch: estimated {est_freq:.2f} Hz, expected"
            f" {expected_freq:.1f} Hz "
            f"(error {err_pct:.2f}% exceeds strict {tolerance * 100:.1f}% threshold)"
        )
        print(
            f"[audio_analyzer] POSITIVE CHECK PASS: Fundamental frequency strictly"
            f" verified ({est_freq:.2f} Hz, error: {err_pct:.3f}% <="
            f" {tolerance * 100:.1f}%)"
        )
        return {
            "status": "PASS",
            "est_freq": est_freq,
            "expected_freq": expected_freq,
            "err_pct": err_pct,
            "rms": rms,
            "sample_rate": sample_rate,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Strict Sample-Spec Aware Audio PCM Analyzer"
    )
    parser.add_argument("raw_file", help="Path to raw S16LE stereo PCM file")
    parser.add_argument(
        "expected_freq", type=float, help="Expected fundamental frequency (Hz)"
    )
    parser.add_argument(
        "--rate", type=int, default=48000, help="Sampling rate in Hz (default: 48000)"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Max relative error tolerance (default: 0.01 = 1%%)",
    )
    parser.add_argument(
        "--expect-fail", action="store_true", help="Expect frequency mismatch rejection"
    )
    parser.add_argument(
        "--crosstalk-freq",
        type=float,
        default=None,
        help="Check tone isolation against foreign frequency",
    )
    args = parser.parse_args()

    analyze_pcm(
        args.raw_file,
        args.expected_freq,
        sample_rate=args.rate,
        tolerance=args.tolerance,
        expect_fail=args.expect_fail,
        crosstalk_freq=args.crosstalk_freq,
    )


if __name__ == "__main__":
    main()
