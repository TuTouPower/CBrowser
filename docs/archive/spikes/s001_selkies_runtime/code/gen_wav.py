import math
import struct
import wave

# Generate 2 seconds of 440Hz sine wave, 44100Hz 16-bit stereo PCM
sample_rate = 44100
duration = 2.0
freq = 440.0
total_samples = int(sample_rate * duration)

with wave.open('/tmp/test_sine.wav', 'wb') as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    data = bytearray()
    for i in range(total_samples):
        t = float(i) / sample_rate
        val = int(32767.0 * 0.8 * math.sin(2.0 * math.pi * freq * t))
        val = max(-32768, min(32767, val))
        sample = struct.pack('<hh', val, val)
        data.extend(sample)
    wf.writeframes(data)

print(f"Generated /tmp/test_sine.wav ({len(data)} bytes)")
