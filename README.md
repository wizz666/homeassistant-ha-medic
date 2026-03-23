# HA Medic 🩺

**AI-powered log diagnostics for Home Assistant**

HA Medic watches your Home Assistant logs, uses an AI provider to diagnose problems, and presents actionable fix suggestions — which you approve before anything is executed.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

---

## How it works

1. **Observe** — fetches core logs (and add-on logs on HAOS) and filters errors/warnings
2. **Suggest** — sends logs to your chosen AI provider, receives structured findings with fix suggestions
3. **Approve** — you review each suggestion and approve or decline. Nothing runs without your consent.

---

## Features

- Works with **Groq** (free), **OpenRouter**, **Ollama** (local), **LM Studio**, **OpenAI**, **Anthropic**, or any OpenAI-compatible API
- Diff analysis — only **new** problems are notified, no repeated alerts for the same issue
- Optional **push notifications** with Approve/Decline buttons (requires Home Assistant Companion App)
- Optional **scheduled analysis** (every 1–24 hours) or manual trigger
- Add-on log analysis (requires **Home Assistant OS**)
- Supports: `reload_automations`, `reload_scripts`, `reload_all`, `restart_addon` as automated fixes

---

## Installation

### HACS (recommended)
1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `wizz666/homeassistant-ha-medic` as type **Integration**
3. Install **HA Medic** and restart Home Assistant

### Manual
Copy `custom_components/ha_medic/` to your `config/custom_components/` directory and restart.

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration → HA Medic**
2. Choose your AI provider and enter your API key
3. Run your first analysis via **Developer Tools → Services → `ha_medic.analyze`**

### Getting a free API key

| Provider | Where to get it | Free tier |
|---|---|---|
| **Groq** | [console.groq.com](https://console.groq.com) | Yes — generous free tier |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | Yes — several free models |
| **Ollama** | Run locally | Fully local, no key needed |

---

## Sensors

| Entity | Description |
|---|---|
| `sensor.ha_medic_status` | `idle` / `analyzing` / `ok` / `error` |
| `sensor.ha_medic_findings` | Number of findings. Attributes include full findings list. |
| `sensor.ha_medic_pending` | Number of pending fix approvals |

---

## Services

| Service | Description |
|---|---|
| `ha_medic.analyze` | Trigger a log analysis |
| `ha_medic.approve` | Approve (and run) the first pending fix, or specify `fix_id` |
| `ha_medic.decline` | Decline a fix suggestion |
| `ha_medic.dismiss_all` | Clear all pending suggestions |

---

## Dashboard

A ready-to-use Lovelace dashboard is included in `extras/dashboard_ha_medic.yaml`.

---

## Notes

- **Add-on logs** require Home Assistant OS (HAOS). On HA Container or Core, only core logs are analyzed.
- The integration stores a queue file (`.ha_medic_queue.json`) and findings cache (`.ha_medic_last_findings.json`) in your config directory.
- Auto-fix runs **only after you approve** each suggestion. Nothing happens automatically.
