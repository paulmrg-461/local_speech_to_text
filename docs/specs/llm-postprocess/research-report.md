# Research — Post-proceso con LLM local (Gemma 4)

Fecha: 2026-11-23 · Estado: cerrado (fase 1) · Autor: DevPaul

## 1. Pregunta

¿Aporta un LLM local (Gemma 4 vía Ollama) al dictado sin degradar latencia,
privacidad ni precisión?

## 2. Contexto medido

| Dato | Valor |
|---|---|
| GPU | RTX 5070, 12.227 MiB |
| Whisper daemon en VRAM | ~3,7 GB (`large-v3-turbo`, float16) |
| Libre aproximado | ~8,4 GB |
| Ollama | 0.40.17 instalado y activo en `127.0.0.1:11434` |
| `gemma4:e4b` (Ollama) | 6,6 GB (Text, Image input; 128K) |
| `gemma4:e2b` | 4,6 GB |
| `gemma4:12b` | 8,0 GB → total ~11,7 GB: no recomendable |

## 3. Dónde aporta y dónde no

| Uso | Veredicto |
|---|---|
| Reemplazar faster-whisper | ❌ sin streaming/timestamps, latencia y VRAM peores |
| Wake word | ❌ un LLM no es un detector always-on |
| Puntuación hablada | ❌ `text_cleaner` es determinista y gratis |
| **Traducción EN→ES** (Whisper solo traduce a inglés) | ✅ resuelve un límite real |
| **Redacción por estilo** (email/chat/código) | ✅ opt-in, valor claro |
| Correcciones de nombres | ⚠️ riesgo de inventar; no en camino crítico |

## 4. Restricciones

1. **Latencia**: el dictado actual pega en <1 s. Un LLM añade 0,3–2 s; debe ser
   opt-in y con timeout duro + fallback al texto crudo.
2. **VRAM**: E4B (6,6 GB) + Whisper (3,7 GB) = ~10,3 GB; entra, pero sin margen
   para 12B. E2B es la alternativa segura.
3. **Privacidad**: solo `localhost`; nada de APIs cloud.
4. **Determinismo/calidad**: temperatura 0, prompt cerrado, salida saneada
   (sin fences/comillas), y nunca pegar dos veces.

## 5. Recomendación

Integración **opcional** por HTTP a Ollama (`/api/generate`), modelo
`gemma4:e4b`, timeout 6 s, `keep_alive=5m`, modos `format` y `translate`.
La transcripción cruda se usa si el LLM falla o tarda. Sin dependencias Python
nuevas (stdlib).
