import numpy as np

from local_speech_to_text.config import Config
from local_speech_to_text.daemon import Daemon
from local_speech_to_text.recorder import AudioRecorder


class FakeRecorder:
    sample_rate = 16000

    def __init__(self, audio):
        self._audio = audio

    def full_audio(self):
        return self._audio


class FakeRecording:
    def __init__(self, audio):
        self.samples = audio
        self.sample_rate = 16000


class FakeTranscriber:
    """Registra qué tramos se le piden y devuelve texto según el tamaño."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, sr):
        self.calls.append(("final", audio.size))
        return f"final[{audio.size}]"

    def transcribe_partial(self, audio, sr):
        self.calls.append(("partial", audio.size))
        return f"partial[{audio.size}]"


def test_streaming_cola_solo_transcribe_lo_pendiente():
    d = Daemon.__new__(Daemon)  # sin recorder real
    d.config = Config.load()
    d.transcriber = FakeTranscriber()
    d._stream_text = "uno dos tres"
    d._stream_processed = 48000  # 3s ya confirmados
    audio = np.zeros((65600,), dtype=np.float32)  # 4.1s total -> cola 1.1s
    d.recorder = FakeRecorder(audio)

    text = d._final_transcription(FakeRecording(audio))
    tail = audio.size - 48000
    assert d.transcriber.calls[-1] == ("final", tail)
    assert text == f"uno dos tres final[{tail}]"


def test_sin_streaming_paso_completo():
    d = Daemon.__new__(Daemon)
    d.config = Config.load()
    d.transcriber = FakeTranscriber()
    d._stream_text = ""  # corto: nunca hubo commits
    d._stream_processed = 0
    d.recorder = FakeRecorder(np.zeros((32000,), dtype=np.float32))

    text = d._final_transcription(FakeRecording(np.zeros((32000,), dtype=np.float32)))
    assert d.transcriber.calls == [("final", 32000)]
    assert text == "final[32000]"


def test_cola_muy_corta_se_omite():
    d = Daemon.__new__(Daemon)
    d.config = Config.load()
    d.transcriber = FakeTranscriber()
    d._stream_text = "texto confirmado"
    d._stream_processed = 48000
    d.recorder = FakeRecorder(np.zeros((48400,), dtype=np.float32))  # cola 0.25s < 0.5s

    text = d._final_transcription(FakeRecording(np.zeros((48400,), dtype=np.float32)))
    # umbral: sr//2 = 8000; cola 400 < 8000 -> sin llamada
    assert d.transcriber.calls == []
    assert text == "texto confirmado"


def test_recorder_full_audio_thread_safe():
    r = AudioRecorder()
    with r._buf_lock:
        r._buffers = [np.ones((16000,), dtype=np.float32), np.zeros((16000,), dtype=np.float32)]
    assert r.full_audio().size == 32000
