import asyncio
import logging
import shutil

logger = logging.getLogger("hermes.plugins.megaphone")

TERMUX_VOLUME = shutil.which("termux-volume") or "/data/data/com.termux/files/usr/bin/termux-volume"
TERMUX_TTS = shutil.which("termux-tts-speak") or "/data/data/com.termux/files/usr/bin/termux-tts-speak"


async def _speak_handler(raw_args: str) -> str:
    message = (raw_args or "").strip()
    if not message:
        return (
            "📢 *Megáfono Doméstico Android*\n\n"
            "Uso: `/di <mensaje>` o `/habla <mensaje>`\n"
            "Ejemplo: `/di ¡Hola a todos! La cena está lista.`\n\n"
            "_El mensaje sonará por el altavoz físico del móvil a volumen 15/15 sin consumir tokens ni latencia LLM._"
        )

    # 1. Ajustar volumen al máximo en el stream multimedia (15/15)
    try:
        vol_proc = await asyncio.create_subprocess_exec(
            TERMUX_VOLUME,
            "music",
            "15",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(vol_proc.communicate(), timeout=5.0)
    except Exception as e:
        logger.warning("Fallo al ajustar volumen en megáfono: %s", e)

    # 2. Emitir el mensaje con termux-tts-speak vía stream MUSIC y lenguaje en español
    try:
        tts_proc = await asyncio.create_subprocess_exec(
            TERMUX_TTS,
            "-s",
            "MUSIC",
            "-l",
            "es-ES",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            tts_proc.communicate(input=message.encode("utf-8")),
            timeout=15.0,
        )
        if tts_proc.returncode != 0:
            err = (stderr or stdout).decode("utf-8", errors="replace").strip()
            return f"⚠️ Error emitiendo por altavoz: {err or tts_proc.returncode}"
    except asyncio.TimeoutError:
        return "⚠️ Tiempo de espera agotado al comunicar con el sintetizador de voz de Android."
    except Exception as e:
        logger.error("Error en termux-tts-speak: %s", e, exc_info=True)
        return f"⚠️ Error inesperado en el megáfono: {e}"

    return f"🔊 *Megáfono emitido a volumen 15/15:*\n«{message}»"


def register(ctx) -> None:
    ctx.register_command(
        name="di",
        handler=_speak_handler,
        description="Emite mensaje por altavoz del móvil a tope de volumen",
        args_hint="<mensaje>",
    )
    ctx.register_command(
        name="habla",
        handler=_speak_handler,
        description="Emite mensaje por altavoz del móvil a tope de volumen",
        args_hint="<mensaje>",
    )
