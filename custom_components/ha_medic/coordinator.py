"""HA Medic coordinator — log fetching, AI analysis, queue management."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_AI_KEY,
    CONF_AI_PROVIDER,
    CONF_AI_BASE_URL,
    CONF_AI_MODEL,
    CONF_INCLUDE_ADDON_LOGS,
    PROVIDER_PRESETS,
    SYSTEM_PROMPT,
)

_LOGGER = logging.getLogger(__name__)


class HaMedicCoordinator:
    """Manages HA Medic state: log fetch, AI call, queue."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.status: str = "idle"
        self.findings: list[dict] = []
        self.summary: str = ""
        self.last_run: str | None = None
        self.pending: list[dict] = []
        self._queue_file = Path(hass.config.path(".ha_medic_queue.json"))
        self._findings_file = Path(hass.config.path(".ha_medic_last_findings.json"))
        self._listeners: list = []

    # ── Listeners ────────────────────────────────────────────────────────────

    def async_add_listener(self, update_callback) -> None:
        self._listeners.append(update_callback)

    def _notify_listeners(self) -> None:
        for cb in self._listeners:
            cb()

    # ── Persistence ──────────────────────────────────────────────────────────

    async def _load_queue(self) -> list[dict]:
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._queue_file.read_text
            )
            return json.loads(text)
        except Exception:
            return []

    async def _save_queue(self, queue: list[dict]) -> None:
        data = json.dumps(queue, ensure_ascii=False, indent=2)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._queue_file.write_text(data, encoding="utf-8")
        )

    async def _load_last_findings(self) -> set[str]:
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._findings_file.read_text
            )
            return set(json.loads(text))
        except Exception:
            return set()

    async def _save_last_findings(self, findings: list[dict]) -> None:
        keys = [self._finding_key(f) for f in findings]
        data = json.dumps(keys, ensure_ascii=False)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._findings_file.write_text(data, encoding="utf-8")
        )

    @staticmethod
    def _finding_key(finding: dict) -> str:
        return f"{finding.get('category', '')}/{finding.get('title', '')[:60]}"

    # ── Log fetching ─────────────────────────────────────────────────────────

    @staticmethod
    def _strip_ansi(text: str) -> str:
        return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)

    @staticmethod
    def _process_logs(raw: str, max_lines: int = 300) -> str:
        clean = HaMedicCoordinator._strip_ansi(raw)
        error_lines = [
            l for l in clean.splitlines()
            if any(k in l for k in ("ERROR", "WARNING", "CRITICAL"))
        ]
        seen: list[str] = []
        unique: list[str] = []
        for line in error_lines:
            key = re.sub(r"\d{2}:\d{2}:\d{2}\.\d+", "", line)[:120]
            if key not in seen:
                seen.append(key)
                unique.append(line)
        return "\n".join(unique[-max_lines:])

    async def _fetch_core_logs(self) -> str:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return ""
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://supervisor/core/logs",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    return await resp.text(encoding="utf-8", errors="replace")
        except Exception as e:
            _LOGGER.warning("HA Medic: failed to fetch core logs: %s", e)
            return ""

    async def _fetch_addon_list(self) -> list[dict]:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return []
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://supervisor/addons",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
            return data.get("data", {}).get("addons", [])
        except Exception:
            return []

    async def _fetch_addon_logs(self, slug: str) -> str:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return ""
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://supervisor/addons/{slug}/logs",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        return ""

    async def _build_log_context(self) -> str:
        sections: list[str] = []
        raw = await self._fetch_core_logs()
        if raw:
            errors = self._process_logs(raw, max_lines=200)
            if errors.strip():
                sections.append(f"=== CORE ===\n{errors}")

        include_addons = self.entry.options.get(
            CONF_INCLUDE_ADDON_LOGS,
            self.entry.data.get(CONF_INCLUDE_ADDON_LOGS, True),
        )
        if include_addons and os.environ.get("SUPERVISOR_TOKEN"):
            addons = await self._fetch_addon_list()
            for addon in addons:
                if addon.get("state") != "started":
                    continue
                slug = addon.get("slug", "")
                name = addon.get("name", slug)
                try:
                    raw = await self._fetch_addon_logs(slug)
                    if not raw.strip():
                        continue
                    errors = self._process_logs(raw, max_lines=80)
                    if errors.strip():
                        sections.append(f"=== ADDON: {name} ({slug}) ===\n{errors}")
                except Exception:
                    pass

        return "\n\n".join(sections)

    # ── AI calls ─────────────────────────────────────────────────────────────

    async def _call_openai_compat(
        self, api_key: str, prompt: str, base_url: str, model: str
    ) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1800,
            "response_format": {"type": "json_object"},
        }
        url = base_url.rstrip("/") + "/chat/completions"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, api_key: str, prompt: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1800,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()
        return data["content"][0]["text"]

    @staticmethod
    def _extract_json(text) -> dict:
        if isinstance(text, dict):
            return text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"No JSON in response: {text[:200]}")

    def _resolve_provider(self) -> tuple[str, str, str, str]:
        """Return (provider, api_key, base_url, model)."""
        data = self.entry.data
        opts = self.entry.options

        provider = opts.get(CONF_AI_PROVIDER, data.get(CONF_AI_PROVIDER, "groq"))
        api_key = opts.get(CONF_AI_KEY, data.get(CONF_AI_KEY, ""))
        base_url = opts.get(CONF_AI_BASE_URL, data.get(CONF_AI_BASE_URL, ""))
        model = opts.get(CONF_AI_MODEL, data.get(CONF_AI_MODEL, ""))

        preset = PROVIDER_PRESETS.get(provider, {})
        if not base_url:
            base_url = preset.get("base_url", "")
        if not model:
            model = preset.get("model", "llama-3.3-70b-versatile")
        if not api_key and "api_key" in preset:
            api_key = preset["api_key"]

        return provider, api_key, base_url, model

    # ── Fix execution ─────────────────────────────────────────────────────────

    async def execute_fix(self, item: dict) -> tuple[bool, str]:
        fix_type = item.get("fix_type", "manual")
        fix_params = item.get("fix_params") or {}

        if fix_type == "reload_automations":
            await self.hass.services.async_call("automation", "reload")
            return True, "Automations reloaded."
        if fix_type == "reload_scripts":
            await self.hass.services.async_call("script", "reload")
            return True, "Scripts reloaded."
        if fix_type == "reload_all":
            await self.hass.services.async_call("homeassistant", "reload_all")
            return True, "All configuration reloaded."
        if fix_type == "restart_addon":
            slug = fix_params.get("addon_slug", "")
            if not slug:
                return False, "fix_params.addon_slug missing."
            token = os.environ.get("SUPERVISOR_TOKEN", "")
            if not token:
                return False, "Supervisor not available (HAOS only)."
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://supervisor/addons/{slug}/restart",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (200, 204):
                        return True, f"Addon '{slug}' restarted."
                    body = await resp.text()
                    return False, f"Restart failed ({resp.status}): {body[:100]}"
        return False, "Manual action required."

    # ── Main analysis ─────────────────────────────────────────────────────────

    async def async_analyze(self) -> None:
        provider, api_key, base_url, model = self._resolve_provider()

        if not api_key and provider not in ("ollama", "lmstudio"):
            self._set_error("API key missing. Configure it in the integration options.")
            return
        if not base_url and provider not in ("anthropic",):
            self._set_error(f"No base URL for provider '{provider}'.")
            return

        self.status = "analyzing"
        self._notify_listeners()

        log_text = await self._build_log_context()

        if not log_text.strip():
            self.findings = []
            self.summary = "No errors or warnings found."
            self.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.status = "ok"
            await self._save_last_findings([])
            self._notify_listeners()
            return

        prompt = f"Analyze these Home Assistant error logs (split by source):\n\n{log_text}"

        try:
            if provider == "anthropic":
                raw = await self._call_anthropic(api_key, prompt)
            else:
                raw = await self._call_openai_compat(api_key, prompt, base_url, model)

            parsed = self._extract_json(raw)
        except Exception as e:
            _LOGGER.error("HA Medic: AI call failed: %s", e)
            self._set_error(f"AI call failed: {e}")
            return

        findings = parsed.get("findings", [])
        self.summary = parsed.get("summary", f"{len(findings)} findings")
        self.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")

        last_keys = await self._load_last_findings()
        for f in findings:
            f["is_new"] = self._finding_key(f) not in last_keys
        await self._save_last_findings(findings)

        self.findings = findings
        self.status = "ok"

        queue = await self._load_queue()
        existing_keys = {q.get("title", "")[:60] for q in queue}
        new_items = 0
        new_manual: list[dict] = []

        for i, finding in enumerate(findings):
            if not finding.get("is_new", True):
                continue
            fix_type = finding.get("fix_type", "manual")
            title_key = finding.get("title", "")[:60]
            if title_key in existing_keys:
                continue
            if fix_type == "manual":
                new_manual.append(finding)
                continue
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fix_id = f"{ts}_{i}"
            queue.append({
                "id": fix_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "title": finding.get("title", ""),
                "description": finding.get("description", ""),
                "suggestion": finding.get("suggestion", ""),
                "fix_type": fix_type,
                "fix_params": finding.get("fix_params") or {},
                "severity": finding.get("severity", "info"),
                "category": finding.get("category", "other"),
            })
            new_items += 1
            existing_keys.add(title_key)

        await self._save_queue(queue)
        self.pending = queue

        # Always notify when findings exist
        if findings:
            lines = []
            for f in findings[:10]:
                icon = "🔴" if f.get("severity") == "error" else "🟡"
                fix = f.get("fix_type", "manual")
                tag = " *(auto-fix available)*" if fix != "manual" else ""
                lines.append(
                    f"{icon} **{f.get('title','')}**{tag}\n"
                    f"{f.get('suggestion','')}"
                )
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": f"HA Medic — {self.summary}",
                    "message": "\n\n".join(lines),
                    "notification_id": "ha_medic_findings",
                },
            )

        _LOGGER.info("HA Medic: analysis done — %s, %d new in queue", self.summary, new_items)
        self._notify_listeners()

    def _set_error(self, msg: str) -> None:
        self.status = "error"
        self.summary = msg
        self._notify_listeners()

    # ── Queue actions ─────────────────────────────────────────────────────────

    async def async_approve(self, fix_id: str | None = None) -> None:
        queue = await self._load_queue()
        if not queue:
            return
        if not fix_id:
            fix_id = queue[0]["id"]

        item = next((q for q in queue if q.get("id") == fix_id), None)
        if not item:
            return

        success, msg = await self.execute_fix(item)
        queue = [q for q in queue if q.get("id") != fix_id]
        await self._save_queue(queue)
        self.pending = queue

        await self.hass.services.async_call(
            "persistent_notification", "dismiss",
            {"notification_id": f"ha_medic_{fix_id}"},
        )
        if success:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "HA Medic: Fix applied",
                    "message": f"**{item['title']}**\n\n{msg}",
                    "notification_id": f"ha_medic_{fix_id}_done",
                },
            )
        else:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "HA Medic: Manual action needed",
                    "message": f"**{item['title']}**\n\n{item['suggestion']}",
                    "notification_id": f"ha_medic_{fix_id}_done",
                },
            )
        self._notify_listeners()

    async def async_decline(self, fix_id: str | None = None) -> None:
        queue = await self._load_queue()
        if not fix_id:
            fix_id = queue[0]["id"] if queue else None
        if not fix_id:
            return
        queue = [q for q in queue if q.get("id") != fix_id]
        await self._save_queue(queue)
        self.pending = queue
        await self.hass.services.async_call(
            "persistent_notification", "dismiss",
            {"notification_id": f"ha_medic_{fix_id}"},
        )
        self._notify_listeners()

    async def async_dismiss_all(self) -> None:
        queue = await self._load_queue()
        for item in queue:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": f"ha_medic_{item['id']}"},
            )
        await self._save_queue([])
        self.pending = []
        self._notify_listeners()

    async def async_load_queue(self) -> None:
        self.pending = await self._load_queue()
