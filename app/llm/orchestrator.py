from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import LLMClient
from app.llm.tools.executor import execute_tool
from app.llm.tools.registry import ToolRegistry

log = get_logger()

SYSTEM_PROMPT = """
Sen bir tool-orchestrator'sun.
- SQL üretme. Sadece verilen tool'ları çağır.
- minutes parametresi integer olmalı.
- Kullanıcı "son 1 saat / geçen 30 dk / bugün / şu an" gibi zaman ifadeleri kullanırsa, tool çağrısında minutes parametresini buna göre doldur.
- Tool sonucu geldiyse "imkansız" deme; sonuç null ise "bu aralıkta veri yok" diye cevap ver.
- Tool çağırman gerekiyorsa JSON'u metin olarak yazma; tool_calls ile çağır.
""".strip()

_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

_TR_NUM = {
    "bir": 1,
    "iki": 2,
    "uc": 3, "üç": 3,
    "dort": 4, "dört": 4,
    "bes": 5, "beş": 5,
    "alti": 6, "altı": 6,
    "yedi": 7,
    "sekiz": 8,
    "dokuz": 9,
    "on": 10,
    "on bir": 11, "onbir": 11,
    "on iki": 12, "oniki": 12,
    "on üç": 13, "onuc": 13, "onüç": 13,
    "on dört": 14, "ondort": 14, "ondört": 14,
    "on beş": 15, "onbes": 15, "onbeş": 15,
    "on altı": 16, "onalti": 16, "onaltı": 16,
    "on yedi": 17, "onyedi": 17,
    "on sekiz": 18, "onsekiz": 18,
    "on dokuz": 19, "ondokuz": 19,
    "yirmi": 20,
    "otuz": 30,
    "kirk": 40, "kırk": 40,
    "elli": 50,
    "altmis": 60, "altmış": 60,
}

_TIME_WINDOW_RE = re.compile(
    r"\b(?:son|gecen|geçen|last)\s+"
    r"(?P<num>\d+|[a-zçğıöşü\s]+)\s*"
    r"(?P<unit>dk|dakika|saat|gun|gün)\b",
    re.IGNORECASE,
)

_NOW_WORDS_RE = re.compile(r"\b(şu an|su an|şimdi|simdi|anlık|anlik)\b", re.IGNORECASE)
_TODAY_RE = re.compile(r"\b(bugün|bugun)\b", re.IGNORECASE)


def _looks_like_escape_answer(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["imkansız", "imkansiz", "impossible", "cannot", "can't"])


def _looks_like_no_data(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["veri yok", "no data", "null", "bulunamad", "yok."])


def _word_or_digit_to_int(s: str) -> int | None:
    if not s:
        return None
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    s = re.sub(r"\s+", " ", s)
    return _TR_NUM.get(s)


def infer_minutes_from_text(user_text: str) -> int | None:
    t = (user_text or "").strip()
    if not t:
        return None
    tl = t.lower()

    if "yarım saat" in tl or "yarim saat" in tl:
        return 30

    m = _TIME_WINDOW_RE.search(tl)
    if m:
        num_raw = (m.group("num") or "").strip()
        unit = (m.group("unit") or "").strip().lower()

        n = _word_or_digit_to_int(num_raw)
        if n is None:
            return None

        if unit in {"dk", "dakika"}:
            minutes = n
        elif unit == "saat":
            minutes = n * 60
        elif unit in {"gun", "gün"}:
            minutes = n * 1440
        else:
            return None

        return max(1, min(1440, minutes))

    # bugün/şimdi basit varsayımlar
    if _TODAY_RE.search(tl):
        return 1440
    if _NOW_WORDS_RE.search(tl):
        return 5

    return None


def _try_parse_inline_tool_json(content: str) -> tuple[str, dict[str, Any]] | None:
    c = (content or "").strip()
    if not (c.startswith("{") and c.endswith("}")):
        return None

    c = _TRAILING_COMMA_RE.sub(r"\1", c)

    try:
        obj = json.loads(c)
    except Exception:
        return None

    if isinstance(obj, dict) and "name" in obj and "parameters" in obj and isinstance(obj["parameters"], dict):
        return obj["name"], obj["parameters"]
    if isinstance(obj, dict) and "tool_name" in obj and "tool_args" in obj and isinstance(obj["tool_args"], dict):
        return obj["tool_name"], obj["tool_args"]

    return None


def _tool_accepts_minutes(registry: ToolRegistry, tool_name: str) -> bool:
    try:
        spec = registry.get(tool_name)
    except Exception:
        return False
    props = (spec.parameters or {}).get("properties") or {}
    return "minutes" in props


def _apply_inferred_minutes_if_needed(
    registry: ToolRegistry,
    tool_name: str,
    tool_args: dict[str, Any],
    inferred_minutes: int | None,
) -> dict[str, Any]:
    if inferred_minutes is None:
        return tool_args
    if not _tool_accepts_minutes(registry, tool_name):
        return tool_args

    m = tool_args.get("minutes")
    bad = (m is None) or (m == 0) or (m == "0") or (m == "") or (isinstance(m, str) and m.strip() == "0")
    if bad:
        tool_args["minutes"] = inferred_minutes
    return tool_args


def _fmt_dt(v: Any) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _format_tool_answer(tool_name: str, tool_args: dict[str, Any], result: dict[str, Any]) -> str | None:
    minutes = tool_args.get("minutes")

    if tool_name == "get_max_cpu_usage":
        v = result.get("max_cpu_usage_percent")
        if v is None:
            return f"Son {minutes} dakika içinde CPU max kullanım verisi yok."
        return f"Son {minutes} dakika içinde maksimum CPU kullanımı: %{float(v):.1f}"

    if tool_name == "get_max_cpu_temp":
        v = result.get("max_cpu_temp_c")
        if v is None:
            return f"Son {minutes} dakika içinde CPU sıcaklık verisi yok."
        return f"Son {minutes} dakika içinde maksimum CPU sıcaklığı: {float(v):.1f}°C"

    if tool_name == "get_max_ram_usage_percent":
        v = result.get("max_ram_usage_percent")
        if v is None:
            return f"Son {minutes} dakika içinde RAM kullanım verisi yok."
        return f"Son {minutes} dakika içinde maksimum RAM kullanımı: %{float(v):.1f}"

    if tool_name == "get_max_gpu_utilization":
        v = result.get("max_gpu_utilization_percent")
        if v is None:
            return f"Son {minutes} dakika içinde GPU kullanım verisi yok."
        return f"Son {minutes} dakika içinde maksimum GPU kullanımı: %{float(v):.1f}"

    if tool_name == "get_latest_snapshot":
        snap = result.get("snapshot")
        if not isinstance(snap, dict):
            return "Snapshot verisi yok."

        cpu = snap.get("cpu") or {}
        ram = snap.get("ram") or {}
        gpu = snap.get("gpu") or {}

        lines: list[str] = ["Son metrik snapshot:"]

        cpu_ts = _fmt_dt(cpu.get("ts"))
        if cpu_ts or cpu.get("usage_percent") is not None:
            lines.append(
                f"- CPU @ {cpu_ts}: usage=%{float(cpu.get('usage_percent')):.1f}"
                + (f", temp={float(cpu.get('temperature_c')):.1f}°C" if cpu.get("temperature_c") is not None else "")
                + (f", freq={float(cpu.get('freq_mhz')):.0f} MHz" if cpu.get("freq_mhz") is not None else "")
            )
        else:
            lines.append("- CPU: veri yok")

        ram_ts = _fmt_dt(ram.get("ts"))
        if ram_ts or ram.get("usage_percent") is not None:
            lines.append(
                f"- RAM @ {ram_ts}: used={ram.get('used_mb')} MB, avail={ram.get('available_mb')} MB, usage=%{float(ram.get('usage_percent')):.1f}"
            )
        else:
            lines.append("- RAM: veri yok")

        gpu_ts = _fmt_dt(gpu.get("ts"))
        if gpu_ts or gpu.get("utilization_percent") is not None:
            lines.append(
                f"- GPU @ {gpu_ts}: util=%{float(gpu.get('utilization_percent')):.1f}"
                + (f", temp={float(gpu.get('temperature_c')):.1f}°C" if gpu.get("temperature_c") is not None else "")
                + (f", mem_used={gpu.get('memory_used_mb')} MB" if gpu.get("memory_used_mb") is not None else "")
            )
        else:
            lines.append("- GPU: veri yok / okunamadı")

        return "\n".join(lines)

    return None


def _tool_result_as_text(tool_name: str, tool_args: dict[str, Any], result: dict[str, Any]) -> str:
    minutes = tool_args.get("minutes")

    def kv(**kwargs: Any) -> str:
        return " ".join([f"{k}={v}" for k, v in kwargs.items()])

    if tool_name == "get_max_cpu_usage":
        return kv(tool=tool_name, minutes=minutes, max_cpu_usage_percent=result.get("max_cpu_usage_percent"))
    if tool_name == "get_max_cpu_temp":
        return kv(tool=tool_name, minutes=minutes, max_cpu_temp_c=result.get("max_cpu_temp_c"))
    if tool_name == "get_max_ram_usage_percent":
        return kv(tool=tool_name, minutes=minutes, max_ram_usage_percent=result.get("max_ram_usage_percent"))
    if tool_name == "get_max_gpu_utilization":
        return kv(tool=tool_name, minutes=minutes, max_gpu_utilization_percent=result.get("max_gpu_utilization_percent"))

    if tool_name == "get_latest_snapshot":
        snap = result.get("snapshot")
        if not isinstance(snap, dict):
            return "tool=get_latest_snapshot snapshot=None"
        cpu = snap.get("cpu") or {}
        ram = snap.get("ram") or {}
        gpu = snap.get("gpu") or {}
        return kv(
            tool="get_latest_snapshot",
            cpu_usage_percent=cpu.get("usage_percent"),
            ram_usage_percent=ram.get("usage_percent"),
            gpu_util_percent=gpu.get("utilization_percent"),
        )

    return f"tool={tool_name} result_keys={list(result.keys())}"


def _required_markers(tool_name: str, tool_args: dict[str, Any], result: dict[str, Any]) -> list[str]:
    if tool_name == "get_max_cpu_usage":
        v = result.get("max_cpu_usage_percent")
        return [f"{float(v):.1f}"] if v is not None else []
    if tool_name == "get_max_cpu_temp":
        v = result.get("max_cpu_temp_c")
        return [f"{float(v):.1f}"] if v is not None else []
    if tool_name == "get_max_ram_usage_percent":
        v = result.get("max_ram_usage_percent")
        return [f"{float(v):.1f}"] if v is not None else []
    if tool_name == "get_max_gpu_utilization":
        v = result.get("max_gpu_utilization_percent")
        return [f"{float(v):.1f}"] if v is not None else []
    if tool_name == "get_latest_snapshot":
        snap = result.get("snapshot")
        if isinstance(snap, dict):
            cpu = snap.get("cpu") or {}
            if cpu.get("usage_percent") is not None:
                return [f"{float(cpu.get('usage_percent')):.1f}"]
        return []
    return []


def _contains_all_markers(text: str, markers: list[str]) -> bool:
    if not markers:
        return True
    t = text or ""
    return all(m in t for m in markers)


async def _finalize_with_llm(client: LLMClient, messages: list[dict[str, Any]], formatted: str, markers: list[str]) -> str:
    instruct = (
        "Aşağıdaki bilgi KESİN ve tool çıktısından gelmiştir. "
        "Bu bilgiyi AYNEN kullan. Sayıları/değerleri değiştirme, uydurma ekleme. "
        "Kullanıcıyı bilgilendir; kısa ve net cevap ver.\n\n"
        f"BİLGİ: {formatted}\n"
    )

    payload = {
        "model": client.model,
        "messages": messages + [{"role": "system", "content": instruct}],
        "tools": [],
        "tool_choice": "none",
    }

    try:
        data = await client.chat(payload)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip()
    except Exception:
        log.exception("llm.finalize.error")
        return formatted

    if not content:
        return formatted

    if not _contains_all_markers(content, markers):
        log.info("llm.finalize.fallback", model_answer=content, fallback=formatted, markers=markers)
        return formatted

    return content


async def ask_with_tools(session: AsyncSession, user_text: str) -> dict[str, Any]:
    registry = ToolRegistry()
    client = LLMClient()
    tools = registry.openai_tools()

    inferred_minutes = infer_minutes_from_text(user_text)
    log.info("llm.user_text", user_text=user_text, inferred_minutes=inferred_minutes)

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if inferred_minutes is not None:
        messages.append(
            {"role": "system", "content": f"Kullanıcı zaman aralığı ifadesinden çıkarım: {inferred_minutes} dakika."}
        )
    messages.append({"role": "user", "content": user_text})

    tools_used = 0

    for i in range(settings.llm_max_tool_iterations):
        payload = {
            "model": client.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        log.info("llm.request", iter=i, model=client.model, tools_count=len(tools), messages_count=len(messages))
        data = await client.chat(payload)

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # inline tool json (rare)
        if not tool_calls:
            inline = _try_parse_inline_tool_json(content)
            if inline:
                tool_name, tool_args = inline
                tool_args = tool_args or {}
                tool_args = _apply_inferred_minutes_if_needed(registry, tool_name, tool_args, inferred_minutes)

                result = await execute_tool(registry, session, tool_name, tool_args)
                tools_used += 1

                tool_text = _tool_result_as_text(tool_name, tool_args, result)
                messages.append({"role": "assistant", "content": ""})
                messages.append({"role": "tool", "tool_call_id": f"inline-{i}", "name": tool_name, "content": tool_text})

                formatted = _format_tool_answer(tool_name, tool_args, result)
                if formatted:
                    markers = _required_markers(tool_name, tool_args, result)
                    final_text = await _finalize_with_llm(client, messages, formatted, markers)
                    return {"answer": final_text}
                continue

        # final
        if not tool_calls:
            if tools_used > 0 and (_looks_like_escape_answer(content) or _looks_like_no_data(content)):
                return {"answer": "Tool çalıştı ama model tutarlı cevap üretmedi. Logları kontrol edebilirsin."}
            return {"answer": content}

        # tool_calls
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        last_formatted: str | None = None
        last_tool_name: str | None = None
        last_tool_args: dict[str, Any] | None = None
        last_tool_result: dict[str, Any] | None = None

        for tc in tool_calls:
            fn = (tc.get("function") or {})
            tool_name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"

            log.info("llm.tool_call.raw", tool_name=tool_name, raw_args=raw_args)

            try:
                tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                tool_args = {}

            if isinstance(tool_args, dict):
                tool_args = _apply_inferred_minutes_if_needed(registry, tool_name, tool_args, inferred_minutes)
            else:
                tool_args = {}

            result = await execute_tool(registry, session, tool_name, tool_args)
            tools_used += 1

            tool_text = _tool_result_as_text(tool_name, tool_args, result)
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "name": tool_name, "content": tool_text})

            last_tool_name = tool_name
            last_tool_args = tool_args
            last_tool_result = result
            last_formatted = _format_tool_answer(tool_name, tool_args, result)

        log.info("llm.tool_results.sent", tools_used=tools_used)

        if last_formatted and last_tool_name and last_tool_args is not None and last_tool_result is not None:
            markers = _required_markers(last_tool_name, last_tool_args, last_tool_result)
            final_text = await _finalize_with_llm(client, messages, last_formatted, markers)
            return {"answer": final_text}

    return {"answer": "Tool çağrıları çok kez tekrarlandı; lütfen soruyu daha net sor."}
