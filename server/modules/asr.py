import base64
import json
from vosk import Model, KaldiRecognizer
from server.gateway.protocol import ProtocolError


class Asr:
    def __init__(self, path):
        self.model = Model(str(path))

    def __call__(self, payload):
        output = []
        for segment in payload["segments"]:
            recognizer = KaldiRecognizer(self.model, 16000)
            pcm = base64.b64decode(segment["pcm_b64"], validate=True)
            texts = []
            for offset in range(0, len(pcm), 8000):
                if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
                    texts.append(json.loads(recognizer.Result()).get("text", ""))
            texts.append(json.loads(recognizer.FinalResult()).get("text", ""))
            text = "".join(texts).replace(" ", "").strip()
            output.append({key: segment[key] for key in ("segment_id", "start_sample", "end_sample")} | {"text": text})
        full_text = "\n".join(item["text"] for item in output if item["text"])
        if not full_text:
            raise ProtocolError("NO_TRANSCRIPT", "No transcript")
        return {"transcript": {"full_text": full_text, "segments": output}}
