"""Strict desktop WAV import; return the same PCM payload used by Android."""
import base64
import wave
from server.gateway.protocol import ProtocolError, MAX_SAMPLES


def read_wav(path):
    try:
        with wave.open(str(path), 'rb') as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (16000, 1, 2, 'NONE'):
                raise ValueError('Expected 16 kHz mono s16le PCM')
            count = source.getnframes()
            if not 0 < count <= MAX_SAMPLES:
                raise ValueError('Duration must be in (0, 60] seconds')
            pcm = source.readframes(count)
            if len(pcm) != count * 2:
                raise ValueError('Truncated WAV data')
    except (OSError, EOFError, ValueError, wave.Error) as error:
        raise ProtocolError('INVALID_PAYLOAD', 'Invalid or unsupported WAV') from error
    return {'audio': {'sample_rate_hz': 16000, 'channels': 1, 'sample_format': 's16le',
                      'sample_count': count, 'pcm_b64': base64.b64encode(pcm).decode()}}
