"""llm.py — Ollama API wrapper for NPC Sim v2"""

import json
import re
import html
import requests
import config


def get_llm_response(prompt: str, model: str = None,
                     timeout: int = config.LLM_TIMEOUT,
                     system: str = "") -> str:
    """Call Ollama and return the full response text.

    Handles both streaming (NDJSON) and single-JSON response formats.
    Returns an empty string on any error.
    """
    model = model or config.OLLAMA_MODEL
    headers = {"Content-Type": "application/json"}
    payload: dict = {"model": model, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system

    try:
        r = requests.post(
            config.OLLAMA_API_URL,
            headers=headers, json=payload,
            timeout=timeout, stream=True,
        )
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[LLM] Request error: {e}")
        return ""

    pieces = []
    try:
        for raw_line in r.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
                if "response" in obj:
                    pieces.append(obj["response"])
            except json.JSONDecodeError:
                pieces.append(raw_line)
    except Exception as e:
        print(f"[LLM] Streaming read error: {e}")

    if pieces:
        return _clean_text("".join(pieces))

    # Fallback: try parsing full body
    try:
        full = r.text
    except Exception:
        return ""

    for ln in full.splitlines():
        try:
            obj = json.loads(ln)
            if "response" in obj:
                pieces.append(obj["response"])
        except Exception:
            pieces.append(ln)

    if pieces:
        return _clean_text("".join(pieces))

    m = re.search(r'"response"\s*:\s*"([^"]*)"', full)
    if m:
        return _clean_text(m.group(1))
    return _clean_text(full)


def parse_npc_response(raw: str) -> tuple[str, str]:
    """Parse 'Dialogue: ...' and 'Action: ...' from LLM output.

    Returns (dialogue, action) both as strings, empty if not found.
    """
    if not raw:
        return "", ""

    # Normalise whitespace around colons
    resp = re.sub(r'\s*:\s*', ':', raw.strip())

    # Try to match Dialogue / Action blocks
    m = re.search(
        r'(?:Dialogue:)?(?P<dialogue>.*?)(?:\s*Action:(?P<action>.*))?$',
        resp, re.IGNORECASE | re.DOTALL,
    )
    if m:
        dialogue = (m.group("dialogue") or "").strip()
        action   = (m.group("action")   or "").strip()
    else:
        lines = [l.strip() for l in resp.splitlines() if l.strip()]
        dialogue, action = "", ""
        if lines:
            if lines[0].lower().startswith("dialogue"):
                dialogue = re.sub(r'(?i)^dialogue[:\s]*', '', lines[0]).strip()
                if len(lines) > 1:
                    action = re.sub(r'(?i)^action[:\s]*', '', lines[1]).strip()
            elif lines[0].lower().startswith("action"):
                action = re.sub(r'(?i)^action[:\s]*', '', lines[0]).strip()
            else:
                if re.search(r'\b(move|attack|say|use|pick|drop)\b', resp, re.IGNORECASE):
                    action = resp.strip()
                else:
                    dialogue = resp.strip()

    dialogue = re.sub(r'(?i)^dialogue[:\s]*', '', dialogue).strip()
    action   = re.sub(r'(?i)^action[:\s]*', '', action).strip()

    # Strip stray "Action:" that leaked into dialogue
    if "Action:" in dialogue:
        dialogue = dialogue.split("Action:")[0].strip()

    return dialogue, action


def parse_storyteller_response(raw: str) -> tuple[str, list[str]]:
    """Parse SITUATION: and EVENT: lines from the storyteller's output.

    Returns (situation_text, [event_strings]).
    """
    situation = ""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("SITUATION:"):
            situation = line.split(":", 1)[1].strip()
        elif line.upper().startswith("EVENT:"):
            events.append(line.split(":", 1)[1].strip())
    return situation, events


# ── Private helpers ────────────────────────────────────────────────────────────

def _clean_text(raw: str) -> str:
    if not raw:
        return ""
    # Try to extract from JSON if the whole response is a JSON object
    try:
        obj = json.loads(raw)
        for key in ("response", "text", "output", "result"):
            if key in obj:
                raw = obj[key]
                break
    except Exception:
        pass

    # Unicode unescape
    try:
        raw = bytes(raw, "utf-8").decode("unicode_escape")
    except Exception:
        pass

    raw = raw.replace("\\", "")
    raw = html.unescape(raw)
    return raw.strip()
