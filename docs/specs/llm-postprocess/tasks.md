# Tareas — Post-proceso con LLM local

> **Estado (2026-11-23):** T1-T5 implementadas y probadas contra Ollama real
> (`gemma4:e4b`); T6 documentado. Falta release (0.4.0) y prueba manual del
> usuario con dictado real.

## T1 · `llm.py` (stdlib)
- `build_prompt`, `sanitize_output`, `ollama_generate`, `postprocess`,
  `llm_status`.
- Tests: prompt por modo/estilo, sanitize, off sin red.

## T2 · Resiliencia
- Timeout duro, HTTP != 200, JSON inválido, `response` vacío → texto original.
- Tests con `urlopen` falso (éxito, error, timeout).

## T3 · Config y TUI
- 6 campos (`post_process`, `llm_model`, `llm_url`, `llm_timeout`,
  `llm_style`, `llm_target_lang`), env y validación.
- Menú TUI (choice/str/float).
- Tests de defaults, env, TOML y valores inválidos.

## T4 · Daemon
- `_apply_llm(text)` tras `numbers_to_digits`; log de latencia.
- Test: off no llama, format llama una vez y respeta fallback.

## T5 · CLI y doctor
- `local-stt llm` (estado, modelos, `--test`, `--check`).
- `doctor`: aviso con URL/modelo/modo; fallo si activo y modelo ausente.
- Tests de `--check` con/sin modelo.

## T6 · Docs y release
- README (sección LLM, VRAM, privacidad, latencia), CHANGELOG, roadmap.
- Medir `gemma4:e4b` real: latencia y VRAM; documentar E2B como alternativa.
- Release 0.4.0 cuando el usuario apruebe.

## Orden

```
T1 → T2 → T3 → T4 → T5 → T6
```
