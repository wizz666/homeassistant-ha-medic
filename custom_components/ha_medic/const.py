"""Constants for HA Medic."""

DOMAIN = "ha_medic"
VERSION = "1.0.0"

CONF_AI_PROVIDER = "ai_provider"
CONF_AI_KEY = "ai_key"
CONF_AI_BASE_URL = "ai_base_url"
CONF_AI_MODEL = "ai_model"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_INCLUDE_ADDON_LOGS = "include_addon_logs"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 0  # 0 = disabled (manual only)
DEFAULT_PROVIDER = "groq"
DEFAULT_INCLUDE_ADDON_LOGS = True

PROVIDERS = ["groq", "openrouter", "ollama", "lmstudio", "openai", "anthropic", "custom"]

PROVIDER_PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2:latest",
        "api_key": "ollama",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
        "api_key": "lm-studio",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}

SYSTEM_PROMPT = """You are a Home Assistant expert analyzing error logs.
ALWAYS respond with valid JSON in exactly this format:
{
  "findings": [
    {
      "severity": "error",
      "category": "zigbee",
      "title": "Short title (max 55 chars)",
      "description": "What is happening (max 180 chars)",
      "suggestion": "Concrete action to take (max 180 chars)",
      "fix_type": "manual",
      "fix_params": {}
    }
  ],
  "summary": "2 errors, 3 warnings found"
}
fix_type values:
  manual            – requires manual action
  reload_automations – run automation.reload
  reload_scripts    – run script.reload
  reload_all        – run homeassistant.reload_all
  restart_addon     – restart an addon; set fix_params: {"addon_slug": "mqtt"}

Common addon_slug values: mqtt (Mosquitto), zigbee2mqtt, esphome, mariadb, studio_code_server.
Rules: max 8 findings, group similar errors, omit trivial MQTT duplicate IDs."""

SIGNAL_UPDATE = f"{DOMAIN}_update"

SCAN_INTERVALS = [0, 1, 3, 6, 12, 24]  # hours, 0 = disabled
