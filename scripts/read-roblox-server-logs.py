#!/usr/bin/env python3
"""Read live Roblox server logs through Open Cloud Server Management."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API_BASE = "https://apis.roblox.com/server-management/v1"
DEFAULT_MAX_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_RETRIES = 4
SEVERITY_LABELS = {
    0: "Output",
    1: "Info",
    2: "Warning",
    3: "Error",
}


class RobloxLogsError(RuntimeError):
    pass


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def require_config(value: str | None, name: str) -> str:
    if not value:
        raise RobloxLogsError(
            f"Missing {name}. Set it in the server-side environment before reading Roblox logs."
        )
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read live Roblox game server logs through Open Cloud.",
    )
    parser.add_argument("--universe-id", default=env_value("ROBLOX_UNIVERSE_ID"))
    parser.add_argument("--place-id", default=env_value("ROBLOX_RACER_PLACE_ID"))
    parser.add_argument("--version-number", default=env_value("ROBLOX_VERSION_NUMBER"))
    parser.add_argument("--api-key-env", default="ROBLOX_API_KEY")
    parser.add_argument("--max-page-size", type=int, default=DEFAULT_MAX_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--min-severity", type=int, default=0)
    parser.add_argument(
        "--warnings-and-errors",
        action="store_true",
        help="Return only Warning and Error logs, equivalent to --min-severity 2.",
    )
    parser.add_argument("--filter", default=None, help="Optional Roblox logs Filter parameter.")
    parser.add_argument("--order-by", default=None, help="Optional Roblox logs OrderBy parameter.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def api_error_message(status: int, body: str) -> str:
    detail = body.strip()
    if status in (401, 403):
        return (
            "Roblox Open Cloud rejected the request. Check that ROBLOX_API_KEY is present, "
            "valid, and has universe:read / server management read permissions for this universe. "
            f"HTTP {status}: {detail}"
        )
    if status == 404:
        return (
            "Roblox Open Cloud returned 404. Check universeId, placeId, versionNumber, "
            f"or jobId. HTTP {status}: {detail}"
        )
    if status == 429:
        return f"Roblox Open Cloud rate limit did not recover after retries. HTTP {status}: {detail}"
    return f"Roblox Open Cloud request failed. HTTP {status}: {detail}"


def request_json(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, headers={"x-api-key": api_key})

    for attempt in range(DEFAULT_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 429 and attempt < DEFAULT_MAX_RETRIES:
                time.sleep(min(2**attempt, 16))
                continue
            raise RobloxLogsError(api_error_message(error.code, body)) from error
        except urllib.error.URLError as error:
            if attempt < DEFAULT_MAX_RETRIES:
                time.sleep(min(2**attempt, 16))
                continue
            raise RobloxLogsError(f"Could not reach Roblox Open Cloud: {error}") from error

    raise RobloxLogsError("Unexpected retry exhaustion while reading Roblox Open Cloud.")


def paged_get(
    path: str,
    api_key: str,
    *,
    item_key: str,
    max_page_size: int,
    max_pages: int,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    page_token = None
    items: list[dict[str, Any]] = []
    for _ in range(max_pages):
        params = {"MaxPageSize": max_page_size, "PageToken": page_token}
        if extra_params:
            params.update(extra_params)
        payload = request_json(path, params, api_key)
        page_items = payload.get(item_key, [])
        if not isinstance(page_items, list):
            raise RobloxLogsError(f"Unexpected Roblox response: {item_key} is not a list.")
        items.extend(page_items)
        page_token = payload.get("nextPageToken")
        if not page_token:
            return items
    raise RobloxLogsError(f"Stopped after {max_pages} pages while reading {path}.")


def severity_label(value: Any) -> str:
    try:
        return SEVERITY_LABELS.get(int(value), f"Unknown({value})")
    except (TypeError, ValueError):
        return f"Unknown({value})"


def normalize_log(entry: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = entry.get("messageTimestampMs")
    timestamp = None
    if isinstance(timestamp_ms, (int, float)):
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp_ms / 1000))
    severity = entry.get("severity")
    return {
        "timestamp": timestamp,
        "universeId": entry.get("universeId"),
        "placeId": entry.get("placeId"),
        "placeVersion": entry.get("placeVersion"),
        "jobId": entry.get("jobId"),
        "severity": severity,
        "severityLabel": severity_label(severity),
        "message": entry.get("message"),
        "stackTrace": entry.get("stackTrace"),
        "context": entry.get("context"),
        "messageTemplate": entry.get("messageTemplate"),
        "skippedCount": entry.get("skippedCount"),
        "rateLimitedCount": entry.get("rateLimitedCount"),
    }


def read_live_server_logs(
    *,
    universe_id: str,
    place_id: str,
    version_number: str,
    api_key: str,
    max_page_size: int,
    max_pages: int,
    min_severity: int,
    log_filter: str | None = None,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    servers_path = (
        f"/universes/{urllib.parse.quote(universe_id)}/places/{urllib.parse.quote(place_id)}"
        f"/versions/{urllib.parse.quote(version_number)}/game-servers"
    )
    servers = paged_get(
        servers_path,
        api_key,
        item_key="gameServers",
        max_page_size=max_page_size,
        max_pages=max_pages,
    )

    logs: list[dict[str, Any]] = []
    for server in servers:
        job_id = server.get("jobId")
        if not job_id:
            continue
        logs_path = f"{servers_path}/{urllib.parse.quote(str(job_id))}/logs"
        server_logs = paged_get(
            logs_path,
            api_key,
            item_key="gameServerLogs",
            max_page_size=max_page_size,
            max_pages=max_pages,
            extra_params={"Filter": log_filter, "OrderBy": order_by},
        )
        for entry in server_logs:
            normalized = normalize_log(entry)
            severity = normalized.get("severity")
            if isinstance(severity, (int, float)) and severity < min_severity:
                continue
            logs.append(normalized)
    return logs


def main() -> int:
    args = parse_args()
    api_key = require_config(os.environ.get(args.api_key_env), args.api_key_env)
    universe_id = require_config(args.universe_id, "ROBLOX_UNIVERSE_ID")
    place_id = require_config(args.place_id, "ROBLOX_RACER_PLACE_ID")
    version_number = require_config(args.version_number, "ROBLOX_VERSION_NUMBER")
    min_severity = 2 if args.warnings_and_errors else args.min_severity

    logs = read_live_server_logs(
        universe_id=universe_id,
        place_id=place_id,
        version_number=version_number,
        api_key=api_key,
        max_page_size=args.max_page_size,
        max_pages=args.max_pages,
        min_severity=min_severity,
        log_filter=args.filter,
        order_by=args.order_by,
    )
    print(json.dumps(logs, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RobloxLogsError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
