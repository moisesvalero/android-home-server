#!/usr/bin/env python3
"""
Módulo de configuración y rutas centralizadas para Android Home Server.
Carga variables de entorno, resuelve directorios y proporciona configuración universal para cualquier LLM.
"""
import os
import sys

def get_hermes_home() -> str:
    """
    Resuelve el directorio base de Hermes/Server en el siguiente orden de prioridad:
    1. Variable de entorno HERMES_HOME
    2. Directorio Termux estándar (/data/data/com.termux/files/home/.hermes) si existe
    3. Fallback estándar a ~/.hermes en el HOME del usuario actual
    """
    if "HERMES_HOME" in os.environ and os.environ["HERMES_HOME"]:
        return os.path.abspath(os.path.expanduser(os.environ["HERMES_HOME"]))
    
    termux_default = "/data/data/com.termux/files/home/.hermes"
    if os.path.exists(termux_default):
        return termux_default
        
    return os.path.abspath(os.path.expanduser("~/.hermes"))

_ENV_LOADED = False
_ENV_CACHE = {}

def load_env(reload: bool = False) -> dict:
    """
    Carga variables desde el archivo .env ubicado en HERMES_HOME o en el directorio actual.
    Retorna un diccionario con las variables cargadas y las inyecta en os.environ si no existían.
    """
    global _ENV_LOADED, _ENV_CACHE
    if _ENV_LOADED and not reload:
        return _ENV_CACHE

    _ENV_CACHE = {}
    hermes_home = get_hermes_home()
    env_paths = [
        os.path.join(hermes_home, ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        os.path.abspath(".env")
    ]

    for path in env_paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        _ENV_CACHE[k] = v
                        if k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                continue

    _ENV_LOADED = True
    return _ENV_CACHE

def get_env_var(key: str, default: str = "") -> str:
    """Obtiene una variable de entorno consultando os.environ y luego el .env cargado."""
    load_env()
    return os.environ.get(key) or _ENV_CACHE.get(key, default)

def get_llm_config() -> dict:
    """
    Devuelve la configuración del LLM activo compatible con la API de OpenAI.
    Detecta automáticamente DeepSeek, OpenAI, Groq, OpenRouter, Gemini u Ollama.
    """
    load_env()
    provider = get_env_var("DEFAULT_LLM_PROVIDER", "").lower()
    
    # 1. DeepSeek (por defecto si no se especifica o si hay clave DeepSeek)
    if provider == "deepseek" or get_env_var("DEEPSEEK_API_KEY"):
        return {
            "provider": "deepseek",
            "api_key": get_env_var("DEEPSEEK_API_KEY"),
            "base_url": get_env_var("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            "model": get_env_var("DEFAULT_LLM_MODEL", "deepseek-flash")
        }
    
    # 2. OpenAI
    if provider == "openai" or get_env_var("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "api_key": get_env_var("OPENAI_API_KEY"),
            "base_url": get_env_var("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            "model": get_env_var("DEFAULT_LLM_MODEL", "gpt-4o-mini")
        }

    # 3. OpenRouter
    if provider == "openrouter" or get_env_var("OPENROUTER_API_KEY"):
        return {
            "provider": "openrouter",
            "api_key": get_env_var("OPENROUTER_API_KEY"),
            "base_url": get_env_var("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            "model": get_env_var("DEFAULT_LLM_MODEL", "deepseek/deepseek-chat")
        }

    # 4. Groq
    if provider == "groq" or get_env_var("GROQ_API_KEY"):
        return {
            "provider": "groq",
            "api_key": get_env_var("GROQ_API_KEY"),
            "base_url": get_env_var("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            "model": get_env_var("DEFAULT_LLM_MODEL", "llama-3.3-70b-versatile")
        }

    # 5. Ollama / Local
    if provider == "ollama" or get_env_var("OLLAMA_BASE_URL"):
        return {
            "provider": "ollama",
            "api_key": "ollama",
            "base_url": get_env_var("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/"),
            "model": get_env_var("DEFAULT_LLM_MODEL", "llama3.2")
        }

    # Fallback genérico
    return {
        "provider": "deepseek",
        "api_key": get_env_var("DEEPSEEK_API_KEY", ""),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash"
    }

def get_scripts_dir() -> str:
    """Devuelve la ruta al directorio de scripts."""
    hermes_scripts = os.path.join(get_hermes_home(), "scripts")
    if os.path.isdir(hermes_scripts):
        return hermes_scripts
    local_scripts = os.path.dirname(os.path.abspath(__file__))
    return local_scripts

def get_script_path(script_name: str) -> str:
    """Resuelve la ruta absoluta de un script, priorizando HERMES_HOME y fallback a local."""
    target_in_hermes = os.path.join(get_hermes_home(), "scripts", script_name)
    if os.path.isfile(target_in_hermes):
        return target_in_hermes
    
    local_target = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    if os.path.isfile(local_target):
        return local_target
        
    return target_in_hermes

if __name__ == "__main__":
    print(f"HERMES_HOME: {get_hermes_home()}")
    print(f"Scripts Dir: {get_scripts_dir()}")
    llm = get_llm_config()
    print(f"LLM Provider: {llm['provider']} | Model: {llm['model']} | Base URL: {llm['base_url']}")
