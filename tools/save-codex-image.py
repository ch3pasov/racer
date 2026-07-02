#!/usr/bin/env python3
import argparse
import base64
import binascii
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SESSION_ROOT = Path.home() / ".codex" / "sessions"
DATA_IMAGE_RE = re.compile(r"^data:image/(?P<format>[-+.\w]+);base64,(?P<data>.*)$", re.DOTALL)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ImageCandidate:
    kind: str
    timestamp: str
    session: Path
    line_no: int
    image_text: str
    source: str
    note: str


def iter_session_paths(args):
    if args.session:
        for session in args.session:
            yield session
        return

    if not args.session_root.exists():
        return

    sessions = sorted(
        (path for path in args.session_root.rglob("*.jsonl") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if args.max_sessions > 0:
        sessions = sessions[: args.max_sessions]
    yield from sessions


def first_input_text(content):
    if not isinstance(content, list):
        return ""
    for item in content:
        if isinstance(item, dict) and item.get("type") == "input_text":
            return " ".join(str(item.get("text", "")).split())[:120]
    return ""


def iter_candidates_from_line(session, line_no, line):
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return

    timestamp = obj.get("timestamp", "")
    payload_type = payload.get("type")

    if payload_type in {"image_generation_call", "image_generation_end"}:
        result = payload.get("result")
        if isinstance(result, str) and result:
            note = " ".join(str(payload.get("revised_prompt", "")).split())[:120]
            source = payload.get("id") or payload.get("call_id") or payload_type
            yield ImageCandidate("generated", timestamp, session, line_no, result, str(source), note)
        return

    if payload_type == "message" and payload.get("role") == "user":
        content = payload.get("content")
        note = first_input_text(content)
        if not isinstance(content, list):
            return
        for index, item in enumerate(content):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "input_image":
                continue
            image_url = item.get("image_url")
            if isinstance(image_url, str) and image_url:
                yield ImageCandidate("input", timestamp, session, line_no, image_url, f"user.content[{index}]", note)
        return

    if payload_type == "user_message":
        note = " ".join(str(payload.get("message", "")).split())[:120]
        images = payload.get("images")
        if not isinstance(images, list):
            return
        for index, image_url in enumerate(images):
            if isinstance(image_url, str) and image_url:
                yield ImageCandidate("input", timestamp, session, line_no, image_url, f"user.images[{index}]", note)


def split_image_text(image_text):
    match = DATA_IMAGE_RE.match(image_text)
    if match:
        return match.group("format").lower(), "".join(match.group("data").split())
    return "png", "".join(image_text.split())


def image_key(image_text):
    image_format, image_base64 = split_image_text(image_text)
    digest = hashlib.sha256(image_base64.encode("ascii", errors="ignore")).hexdigest()
    return image_format, digest


def png_dimensions(data):
    if not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ValueError("decoded image is not a PNG")
    return struct.unpack(">II", data[16:24])


def decode_png(candidate):
    image_format, image_base64 = split_image_text(candidate.image_text)
    try:
        data = base64.b64decode(image_base64, validate=True)
    except binascii.Error as exc:
        raise ValueError(f"invalid base64 image data: {exc}") from exc

    width, height = png_dimensions(data)
    if image_format != "png":
        raise ValueError(f"expected PNG data URL, got image/{image_format}")
    return data, width, height


def collect_candidates(args):
    candidates = []
    for session in iter_session_paths(args):
        if not session.exists():
            continue
        with session.open("r", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                candidates.extend(iter_candidates_from_line(session, line_no, line))

    if args.kind != "any":
        candidates = [candidate for candidate in candidates if candidate.kind == args.kind]

    candidates.sort(key=lambda candidate: (candidate.timestamp, str(candidate.session), candidate.line_no), reverse=True)

    deduped = []
    seen = set()
    for candidate in candidates:
        key = (candidate.kind, image_key(candidate.image_text))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def describe_candidate(index, candidate):
    data, width, height = decode_png(candidate)
    digest = hashlib.sha256(data).hexdigest()[:12]
    print(
        f"{index}: {candidate.kind} {width}x{height} sha256={digest} "
        f"{candidate.timestamp} {candidate.session}:{candidate.line_no} {candidate.source}"
    )
    if candidate.note:
        print(f"   {candidate.note}")


def main():
    parser = argparse.ArgumentParser(
        description="Save a Codex chat/input or built-in image_gen PNG from local session logs."
    )
    parser.add_argument("--kind", choices=["generated", "input", "any"], default="generated")
    parser.add_argument("--output", type=Path, help="PNG path to write")
    parser.add_argument("--index", type=int, default=0, help="0 is the newest matching image")
    parser.add_argument("--list", action="store_true", help="List matching images instead of writing")
    parser.add_argument("--limit", type=int, default=10, help="List limit")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    parser.add_argument("--session", type=Path, action="append", help="Specific Codex JSONL session to scan")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT)
    parser.add_argument("--max-sessions", type=int, default=25, help="0 scans every session")
    args = parser.parse_args()

    candidates = collect_candidates(args)
    if args.list:
        for index, candidate in enumerate(candidates[: args.limit]):
            describe_candidate(index, candidate)
        return

    if args.output is None:
        raise SystemExit("--output is required unless --list is used")
    if args.index < 0 or args.index >= len(candidates):
        raise SystemExit(f"no image candidate at index {args.index}; found {len(candidates)}")
    if args.output.exists() and not args.force:
        raise SystemExit(f"{args.output} already exists; pass --force to overwrite")

    candidate = candidates[args.index]
    data, width, height = decode_png(candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = args.output.with_name(args.output.name + ".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(args.output)
    print(f"saved {candidate.kind} {width}x{height} PNG to {args.output}")
    print(f"source {candidate.session}:{candidate.line_no}")


if __name__ == "__main__":
    main()
