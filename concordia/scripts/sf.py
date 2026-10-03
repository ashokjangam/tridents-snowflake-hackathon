"""Snowflake session helper for deployment scripts. Reads ~/.snowflake/connections.toml."""

from __future__ import annotations

import os
import re
from pathlib import Path

import snowflake.connector

CONNECTION = os.environ.get("CONCORDIA_CONNECTION", "hackathon")
ROOT = Path(__file__).resolve().parents[1]


def _connection_config() -> dict:
    import tomlkit

    path = Path.home() / ".snowflake" / "connections.toml"
    config = dict(tomlkit.parse(path.read_text(encoding="utf-8"))[CONNECTION])
    key_path = config.pop("private_key_path", None)
    if key_path and "private_key_file" not in config:
        config["private_key_file"] = key_path
    for key in ("account", "user"):
        override = os.environ.get(f"CONCORDIA_{key.upper()}")
        if override:
            config[key] = override
            config.pop("host", None)
    return {key: str(value) for key, value in config.items()}


def connect(role: str | None = None, warehouse: str | None = None):
    kwargs = _connection_config()
    kwargs["session_parameters"] = {"QUERY_TAG": "concordia"}
    if role:
        kwargs["role"] = role
    if warehouse:
        kwargs["warehouse"] = warehouse
    return snowflake.connector.connect(**kwargs)


def rows(cur, sql: str, params=None) -> list[dict]:
    cur.execute(sql, params)
    names = [col[0] for col in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def split_sql(text: str) -> list[str]:
    """Split on semicolons outside quotes and $$ blocks; drop comment-only pieces."""
    statements, buf, i = [], [], 0
    in_single = in_dollar = False
    while i < len(text):
        ch = text[i]
        if not in_single and text.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        if not in_dollar and ch == "'":
            in_single = not in_single
        if not in_single and not in_dollar and text.startswith("--", i):
            end = text.find("\n", i)
            end = len(text) if end == -1 else end
            buf.append(text[i:end])
            i = end
            continue
        if ch == ";" and not in_single and not in_dollar:
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    statements.append("".join(buf))
    cleaned = []
    for statement in statements:
        body = "\n".join(line for line in statement.splitlines() if not line.strip().startswith("--")).strip()
        if body:
            cleaned.append(statement.strip())
    return cleaned


def run_file(cur, path: Path, replacements: dict[str, str] | None = None, echo: bool = True) -> None:
    text = path.read_text(encoding="utf-8")
    for key, value in (replacements or {}).items():
        text = text.replace(key, value)
    for statement in split_sql(text):
        first = re.sub(r"\s+", " ", statement)[:110]
        if echo:
            print("  >", first)
        try:
            cur.execute(statement)
        except Exception as exc:
            raise RuntimeError(f"{path.name}: {first}\n{exc}") from None
