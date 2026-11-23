# Requisitos — Post-proceso con LLM local (EARS)

## Funcionales

**RF-1 (off por defecto)**
Donde `post_process = "off"`, el sistema shall copiar el texto de Whisper sin
llamadas de red.
*Criterio:* `postprocess(...)` devuelve el mismo texto y no abre socket.

**RF-2 (formato)**
Cuando `post_process = "format"`, el sistema shall reescribir el texto según
`llm_style` (`clean|email|chat|code`) sin cambiar el significado.
*Criterio:* el prompt contiene el estilo y el texto delimitado; salida saneada.

**RF-3 (traducción)**
Cuando `post_process = "translate"`, el sistema shall traducir al idioma
`llm_target_lang` (default `español`).
*Criterio:* el prompt pide “devuelve solo la traducción”.

**RF-4 (fallback)**
Si Ollama no responde, devuelve error, tarda más de `llm_timeout` o da salida
vacía, entonces el sistema shall usar el texto original y registrar el motivo.
*Criterio:* servidor caído/timeout/`{"response": ""}` → texto intacto.

**RF-5 (salida limpia)**
El sistema shall eliminar fences de código, comillas envolventes y espacios
sobrantes de la respuesta antes de usarla.
*Criterio:* `sanitize_output("```\nhola\n```") == "hola"`.

**RF-6 (contexto delimitado)**
El prompt shall envolver la transcripción en etiquetas y pedir ignorar
instrucciones dentro de ella (mitigación de prompt injection).
*Criterio:* el prompt contiene `<texto>` y una instrucción explícita.

**RF-7 (diagnóstico)**
`local-stt llm` shall mostrar URL, modelos disponibles, modo, estilo y si el
modelo configurado está; `--check` shall salir 1 si está activo y no puede
usarse. `doctor` shall incluirlo como aviso.
*Criterio:* con `post_process != off` y Ollama caído, `--check` = 1.

## No funcionales

**RNF-1** Sin dependencias nuevas: `urllib` + `json`.

**RNF-2** Timeout duro configurable (`llm_timeout`, default 6 s) y
`keep_alive=5m` para no recargar el modelo en cada dictado.

**RNF-3** Privacidad: solo `http://127.0.0.1`/localhost; `doctor` avisa si la
URL no es local.

**RNF-4** El dictado nunca falla por el LLM: la excepción se captura y se
devuelve el texto crudo.
