from __future__ import annotations

import os
from pathlib import Path

import numpy as np


class Transcriber:
    """Wrapper sobre faster-whisper optimizado para RTX 5070 (Blackwell, 12GB)."""

    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str | None = "es",
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        self.model_name = model
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._load()

    def _load(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(
                "Falta 'faster-whisper'. Instala: pip install faster-whisper\n"
                "Para CUDA: asegúrate de tener CUDA 12.x y cuDNN instalados."
            ) from e

        # RTX 5070 Blackwell necesita CUDA 12.8+. Si no hay GPU, fallback a CPU.
        # ctranslate2 hace dlopen de libcublas.so.12: precargamos la del paquete
        # pip (Arch instala CUDA 13 y no la tiene).
        if self.device == "cuda":
            from .cuda_libs import preload_cuda_libs

            preload_cuda_libs()

        device = self.device
        compute = self.compute_type
        if device == "cuda":
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() < 1:
                    raise RuntimeError("No hay dispositivos CUDA")
                self._model = WhisperModel(
                    self.model_name, device="cuda", compute_type=compute, download_root=None
                )
                print(f"[transcriber] Modelo {self.model_name} cargado en CUDA ({compute})")
                return
            except Exception as e:
                print(f"[transcriber] No se pudo cargar en CUDA ({e}), fallback a CPU int8")
                device = "cpu"
                compute = "int8"

        self._model = WhisperModel(self.model_name, device=device, compute_type=compute)
        print(f"[transcriber] Modelo {self.model_name} cargado en {device} ({compute})")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if audio.size == 0:
            return ""
        # faster-whisper acepta ndarray float32 [-1,1] a 16kHz
        # Si no es 16kHz, faster-whisper lo resamplea internamente, pero preferimos ya estar en 16k
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
        )
        text_parts = []
        for seg in segments:
            text_parts.append(seg.text.strip())
        text = " ".join(text_parts).strip()
        # Limpieza ligera
        if text:
            # Capitalizar primera letra si no está
            if text[0].islower():
                text = text[0].upper() + text[1:]
        lang_info = f" lang={info.language} prob={info.language_probability:.2f}" if hasattr(info, "language") else ""
        print(f"[transcriber] Detectado:{lang_info} -> \"{text[:120]}\"")
        return text

    @staticmethod
    def available_models() -> list[str]:
        return ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3"]
