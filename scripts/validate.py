"""校验公开的 LibreTV-SourceList；只读、无依赖、不进行网络请求。"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = (ROOT / "sources/stable.json", ROOT / "sources/all.json")
SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|cookie|authorization|api[-_]?key|credential|signature|^key$|^auth$|^sign$",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    r"gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer\s+\S+|"
    r"(?:password|token|secret|api[-_]?key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
LOCAL_SUFFIXES = (".localhost", ".local", ".lan", ".internal", ".home", ".home.arpa")


class ValidationError(ValueError):
    """错误仅报告字段位置，不回显可能包含凭证的字段值。"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def text(value: object, location: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{location}: expected non-empty string")
    require(not SECRET_VALUE.search(value), f"{location}: possible credential; review before publishing")
    return value


def public_url(value: object, location: str) -> str:
    value = text(value, location)
    require(not any(char.isspace() or ord(char) < 32 for char in value), f"{location}: whitespace in URL")
    require("\\" not in value, f"{location}: backslash in URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        raise ValidationError(f"{location}: malformed URL") from None
    require(parsed.scheme in ("http", "https") and bool(host), f"{location}: expected absolute HTTP(S) URL")
    require(port is None or port > 0, f"{location}: invalid port")
    require(parsed.username is None and parsed.password is None, f"{location}: URL credentials are forbidden")
    require(not parsed.fragment, f"{location}: URL fragments are unsupported")
    require(not any(SENSITIVE_KEY.search(key) for key, _ in parse_qsl(parsed.query)),
            f"{location}: possible secret query parameter; review before publishing")
    require(not re.search(r"/(?:token|secret|api[-_]?key)/[^/]+", unquote(parsed.path), re.I),
            f"{location}: possible secret in URL path; review before publishing")
    require("%" not in host,
            f"{location}: encoded host or IPv6 zone identifier is unsupported")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        require("." in host and not host.endswith(LOCAL_SUFFIXES), f"{location}: local hostname is forbidden")
        # 拒绝浏览器可能解释为 IPv4 的缩写、八进制或十六进制地址。
        require(not re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host),
                f"{location}: ambiguous numeric hostname")
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise ValidationError(f"{location}: invalid hostname") from None
        require(all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in ascii_host.split(".")), f"{location}: invalid hostname")
    else:
        require(address.is_global and not address.is_multicast, f"{location}: non-public IP is forbidden")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            require(address.ipv4_mapped.is_global, f"{location}: non-public mapped IPv4 is forbidden")
    # 仅用于比较，不重写原始 URL；与 LibreTV 的去尾部斜杠行为一致。
    normalized_port = "" if port is None or (parsed.scheme, port) in (("http", 80), ("https", 443)) else f":{port}"
    normalized_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{normalized_host}{normalized_port}{parsed.path.rstrip('/')}" + (f"?{parsed.query}" if parsed.query else "")


def validate_data(data: object) -> tuple[int, int]:
    require(isinstance(data, dict), "$: expected SourceList object, not settings backup or array")
    allowed = {"name", "version", "sources", "liveSources"}
    require(set(data) == allowed, "$: expected only name, version, sources, liveSources")
    text(data["name"], "$.name")
    require(type(data["version"]) is int and data["version"] == 2, "$.version: expected integer 2")
    for group, optional, maximum in (("sources", {"detail", "isAdult"}, 100), ("liveSources", {"epg"}, 50)):
        entries = data[group]
        require(isinstance(entries, list), f"$.{group}: expected array")
        require(len(entries) <= maximum, f"$.{group}: exceeds LibreTV limit of {maximum}")
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            location = f"$.{group}[{index}]"
            require(isinstance(entry, dict), f"{location}: expected object")
            require({"name", "url"} <= set(entry), f"{location}: name and url are required")
            require(set(entry) <= {"name", "url"} | optional, f"{location}: incompatible or sensitive field")
            text(entry["name"], f"{location}.name")
            key = public_url(entry["url"], f"{location}.url")
            require(key not in seen, f"{location}.url: duplicate URL within {group}")
            seen.add(key)
            if "isAdult" in entry:
                require(type(entry["isAdult"]) is bool, f"{location}.isAdult: expected boolean")
            for field in ("detail", "epg"):
                if field in entry:
                    public_url(entry[field], f"{location}.{field}")
    return len(data["sources"]), len(data["liveSources"])


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON contains duplicate object keys")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValidationError("JSON contains non-standard NaN/Infinity")


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ValidationError(f"invalid JSON at line {error.lineno}, column {error.colno}") from None
    except UnicodeError:
        raise ValidationError("file must be UTF-8 JSON") from None


def validate_file(path: Path) -> tuple[int, int]:
    return validate_data(load_json(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="JSON paths; defaults to stable.json and all.json")
    args = parser.parse_args()
    failed = False
    for path in args.files or DEFAULT_FILES:
        try:
            sources, live_sources = validate_file(path)
            print(f"OK {path.name}: sources={sources}, liveSources={live_sources}")
        except (OSError, ValidationError) as error:
            print(f"FAIL {path.name}: {error}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
