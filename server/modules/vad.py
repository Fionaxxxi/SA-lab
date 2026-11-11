import base64
import numpy as np
import onnxruntime as ort
from server.gateway.protocol import ProtocolError, pcm_length


class Vad:
    def __init__(self, path, threshold=0.5):
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.threshold = threshold

    def __call__(self, payload):
        audio = payload["audio"]
        pcm_length(audio["pcm_b64"], audio["sample_count"])
        raw = base64.b64decode(audio["pcm_b64"], validate=True)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(64, dtype=np.float32)
        intervals, start, silence = [], None, 0
        for offset in range(0, len(samples), 512):
            frame = np.zeros(512, dtype=np.float32)
            part = samples[offset:offset + 512]
            frame[:len(part)] = part
            probability, state = self.session.run(None, {"input": np.concatenate((context, frame))[None, :],
                                                        "state": state, "sr": np.asarray(16000, dtype=np.int64)})
            context = frame[-64:]
            if float(probability.flat[0]) >= self.threshold:
                if start is None:
                    start = max(0, offset - 480)
                silence = 0
            elif start is not None:
                silence += 1
                if silence >= 10:
                    intervals.append([start, min(len(samples), offset - 9 * 512 + 480)])
                    start, silence = None, 0
        if start is not None:
            intervals.append([start, len(samples)])
        merged = []
        for left, right in intervals:
            if merged and left <= merged[-1][1]:
                merged[-1][1] = max(right, merged[-1][1])
            else:
                merged.append([left, right])
        if not merged:
            raise ProtocolError("NO_SPEECH", "No speech")
        return {"segments": [{"segment_id": f"seg{i+1}", "start_sample": left, "end_sample": right,
                              "pcm_b64": base64.b64encode(raw[left*2:right*2]).decode()}
                             for i, (left, right) in enumerate(merged)]}
