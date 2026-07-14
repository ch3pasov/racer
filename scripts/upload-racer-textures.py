#!/usr/bin/env python3
import argparse
import binascii
import gzip
import hashlib
import http.client
import json
import os
import re
import secrets
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / "assets/racer/textures/racer-sprites-v3.png"
ASSETS_BASE = "https://apis.roblox.com/assets/v1"
DELIVERY_BASE = "https://apis.roblox.com/asset-delivery-api/v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_EDGE = 8000
EXPECTED_ATLAS_SIZE = (1024, 1024)
TRANSIENT_HTTP_CODES = {408, 429, 500, 502, 503, 504}
TRANSIENT_DELIVERY_CODES = {13, 14, 15, 18, 21}
STATE_PATH = ROOT / "build/racer-texture-upload-state.json"


class UploadError(RuntimeError):
    pass


class HttpFailure(UploadError):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status


class SparseAssetMetadata(UploadError):
    pass


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise UploadError("Authenticated Roblox API request attempted a redirect")


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if urllib.parse.urlsplit(new_url).scheme != "https":
            raise UploadError("Roblox delivery attempted a non-HTTPS redirect")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


API_OPENER = urllib.request.build_opener(NoRedirectHandler())
CDN_OPENER = urllib.request.build_opener(HttpsOnlyRedirectHandler())


def clean_message(value) -> str:
    return " ".join(str(value).split())[:400]


def positive_decimal(value, label: str) -> int:
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise UploadError(f"{label} must be a positive decimal integer")
    return int(text)


def duration_from_env(name: str, default: int) -> float:
    value = os.environ.get(name, str(default))
    try:
        duration = float(value)
    except ValueError as error:
        raise UploadError(f"{name} must be a positive number") from error
    if not 0 < duration <= 24 * 60 * 60:
        raise UploadError(f"{name} must be greater than zero and at most 86400")
    return duration


def parse_png(data: bytes, label: str, expected_size=None):
    if len(data) < 33 or data[:8] != PNG_SIGNATURE:
        raise UploadError(f"{label} is not a valid PNG")
    offset = 8
    header = None
    idat = bytearray()
    saw_end = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise UploadError(f"{label} has a truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_end = offset + 8 + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            raise UploadError(f"{label} has a truncated PNG chunk")
        payload = data[offset + 8 : payload_end]
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        actual_crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise UploadError(f"{label} has a corrupt PNG chunk")
        if kind == b"IHDR":
            if header is not None or offset != 8 or length != 13:
                raise UploadError(f"{label} has an invalid PNG header")
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            if header is None:
                raise UploadError(f"{label} has image data before its header")
            idat.extend(payload)
        elif kind == b"IEND":
            if length != 0 or chunk_end != len(data):
                raise UploadError(f"{label} has an invalid PNG end chunk")
            saw_end = True
            break
        offset = chunk_end
    if header is None or not idat or not saw_end:
        raise UploadError(f"{label} is missing required PNG chunks")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    if width <= 0 or height <= 0 or width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
        raise UploadError(f"{label} has unsupported dimensions {width}x{height}")
    if compression != 0 or filtering != 0 or interlace not in {0, 1}:
        raise UploadError(f"{label} has an unsupported PNG header")
    valid_bit_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if color_type not in valid_bit_depths or bit_depth not in valid_bit_depths[color_type]:
        raise UploadError(f"{label} has an unsupported PNG pixel format")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as error:
        raise UploadError(f"{label} contains invalid compressed pixels") from error
    if interlace == 0:
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
        stride = (width * channels * bit_depth + 7) // 8
        if len(raw) != (stride + 1) * height:
            raise UploadError(f"{label} contains an invalid amount of pixel data")
        if any(raw[row * (stride + 1)] > 4 for row in range(height)):
            raise UploadError(f"{label} contains an invalid PNG row filter")
    if expected_size is not None and (width, height) != expected_size:
        raise UploadError(
            f"{label} must be {expected_size[0]}x{expected_size[1]}, got {width}x{height}"
        )
    return width, height


def read_upload(path: Path) -> bytes:
    if not path.is_file():
        raise UploadError(f"Texture atlas not found: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise UploadError("Texture atlas must be nonempty and no larger than 20 MiB")
    data = path.read_bytes()
    parse_png(data, "Texture atlas", EXPECTED_ATLAS_SIZE)
    return data


def api_request_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
    timeout: float = 60,
):
    headers = {"Accept": "application/json", "x-api-key": api_key}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with API_OPENER.open(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        detail = clean_message(error.read(4096).decode("utf-8", "replace"))
        suffix = f": {detail}" if detail else ""
        raise HttpFailure(error.code, f"Roblox API returned HTTP {error.code}{suffix}") from error
    except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead) as error:
        raise HttpFailure(None, f"Roblox API request failed: {clean_message(error)}") from error
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UploadError("Roblox API returned invalid JSON") from error
    if not isinstance(value, dict):
        raise UploadError("Roblox API returned a non-object JSON response")
    return value


def multipart_body(request_json: dict, image_path: Path, image_data: bytes):
    boundary = f"codex-racer-{secrets.token_hex(16)}"
    boundary_bytes = boundary.encode("ascii")
    request_bytes = json.dumps(request_json, separators=(",", ":")).encode("utf-8")
    filename = re.sub(r'[^A-Za-z0-9._-]', "_", image_path.name)
    body = b"".join(
        [
            b"--" + boundary_bytes + b"\r\n",
            b'Content-Disposition: form-data; name="request"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            request_bytes,
            b"\r\n--" + boundary_bytes + b"\r\n",
            f'Content-Disposition: form-data; name="fileContent"; filename="{filename}"\r\n'.encode(
                "utf-8"
            ),
            b"Content-Type: image/png\r\n\r\n",
            image_data,
            b"\r\n--" + boundary_bytes + b"--\r\n",
        ]
    )
    return body, f"multipart/form-data; boundary={boundary}"


def retrying_get_json(url: str, api_key: str, deadline: float, label: str):
    while True:
        try:
            remaining = max(0.1, deadline - time.monotonic())
            return api_request_json(url, api_key, timeout=min(60, remaining))
        except HttpFailure as error:
            if (
                error.status is not None
                and error.status not in TRANSIENT_HTTP_CODES | {404}
            ) or time.monotonic() >= deadline:
                raise
            print(f"{label}: transient response; retrying", file=sys.stderr)
            time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))


def operation_error(operation):
    error = operation.get("error")
    if not error:
        return None
    if not isinstance(error, dict):
        return "Roblox asset operation failed"
    code = clean_message(error.get("code", "unknown"))
    message = clean_message(error.get("message", "unknown error"))
    return f"Roblox asset operation failed ({code}): {message}"


def operation_id(operation):
    path = operation.get("path")
    if not isinstance(path, str) or not path.startswith("operations/"):
        raise UploadError("Roblox asset response did not contain a valid operation path")
    identifier = path.removeprefix("operations/")
    if not identifier or "/" in identifier or identifier in {".", ".."} or "?" in identifier or "#" in identifier:
        raise UploadError("Roblox asset response did not contain a valid operation path")
    return identifier


def wait_for_operation(operation, api_key: str, timeout: float, poll_interval: float):
    identifier = operation_id(operation)
    deadline = time.monotonic() + timeout
    while True:
        failure = operation_error(operation)
        if failure:
            raise UploadError(failure)
        if operation.get("done") is True:
            response = operation.get("response")
            if not isinstance(response, dict):
                raise UploadError("Completed Roblox asset operation has no response")
            return response
        if time.monotonic() >= deadline:
            raise UploadError("Timed out waiting for Roblox asset creation")
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
        operation = retrying_get_json(
            f"{ASSETS_BASE}/operations/{urllib.parse.quote(identifier, safe='')}",
            api_key,
            deadline,
            "Asset creation",
        )


def normalize_asset_id(value, label: str) -> int:
    if isinstance(value, bool):
        raise UploadError(f"{label} must be a positive asset ID")
    return positive_decimal(value, label)


def require_image_asset(asset, expected_id: int, creator_key=None, creator_id=None):
    for field in ("assetId", "path", "assetType", "revisionId"):
        if asset.get(field) is None:
            raise SparseAssetMetadata(f"Roblox asset metadata omitted {field}")
    asset_id = normalize_asset_id(asset.get("assetId"), "Roblox assetId")
    if asset_id != expected_id or asset.get("path") != f"assets/{expected_id}":
        raise UploadError("Roblox returned metadata for a different asset")
    asset_type = str(asset.get("assetType", "")).upper().removeprefix("ASSET_TYPE_")
    if asset_type != "IMAGE":
        raise UploadError("Roblox created an asset that is not an Image")
    if str(asset.get("state", "")).upper() == "ARCHIVED":
        raise UploadError("Roblox created the texture asset in an archived state")
    revision_id = positive_decimal(asset.get("revisionId"), "Roblox revisionId")
    if creator_key is not None:
        creation_context = asset.get("creationContext")
        creator = creation_context.get("creator") if isinstance(creation_context, dict) else None
        if isinstance(creator, dict):
            if creator.get(creator_key) is not None:
                actual_creator = normalize_asset_id(creator.get(creator_key), f"Roblox {creator_key}")
                if actual_creator != creator_id:
                    raise UploadError("Roblox asset creator does not match the upload request")
            elif creator.get("userId") is not None or creator.get("groupId") is not None:
                raise UploadError("Roblox asset creator kind does not match the upload request")
    return revision_id


def validate_operation_asset(asset, expected_id: int):
    path = asset.get("path")
    if path is not None and path != f"assets/{expected_id}":
        raise UploadError("Roblox operation returned a path for a different asset")
    asset_type = asset.get("assetType")
    if asset_type is not None:
        normalized = str(asset_type).upper().removeprefix("ASSET_TYPE_")
        if normalized != "IMAGE":
            raise UploadError("Roblox operation created an asset that is not an Image")
    revision = asset.get("revisionId")
    return positive_decimal(revision, "Roblox revisionId") if revision is not None else None


def moderation_state(asset) -> str:
    result = asset.get("moderationResult")
    value = result.get("moderationState") if isinstance(result, dict) else ""
    return str(value).upper().removeprefix("MODERATION_STATE_") or "UNKNOWN"


def wait_for_approval(
    asset_id: int,
    api_key: str,
    creator_key: str,
    creator_id: int,
    timeout: float,
    poll_interval: float,
):
    deadline = time.monotonic() + timeout
    last_state = None
    while True:
        asset = retrying_get_json(
            f"{ASSETS_BASE}/assets/{asset_id}", api_key, deadline, "Asset moderation"
        )
        try:
            revision_id = require_image_asset(asset, asset_id, creator_key, creator_id)
        except SparseAssetMetadata:
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
            continue
        state = moderation_state(asset)
        if state != last_state:
            print(f"Asset {asset_id} moderation: {state.lower()}", file=sys.stderr)
            last_state = state
        if state == "APPROVED":
            return revision_id
        if state == "REJECTED":
            raise UploadError(f"Roblox moderation rejected asset {asset_id}")
        if time.monotonic() >= deadline:
            raise UploadError(
                f"Asset {asset_id} is still awaiting moderation after the configured timeout"
            )
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))


def fetch_delivery_json(asset_id: int, revision_id: int, api_key: str, deadline: float):
    url = f"{DELIVERY_BASE}/assetId/{asset_id}/version/{revision_id}"
    return retrying_get_json(url, api_key, deadline, "Asset delivery")


def delivery_errors_are_transient(errors) -> bool:
    if not isinstance(errors, list) or not errors:
        return False
    transient_words = ("pending", "review", "generating", "not found", "not ready", "unavailable")
    for error in errors:
        if not isinstance(error, dict):
            return False
        codes = [error.get("customErrorCode"), error.get("CustomErrorCode"), error.get("code")]
        numeric_codes = set()
        for value in codes:
            try:
                numeric_codes.add(int(value))
            except (TypeError, ValueError):
                pass
        message = " ".join(clean_message(value).lower() for value in error.values())
        if not (numeric_codes & TRANSIENT_DELIVERY_CODES) and not any(
            word in message for word in transient_words
        ):
            return False
    return True


def fetch_cdn_png(location: str) -> bytes:
    if urllib.parse.urlsplit(location).scheme != "https":
        raise UploadError("Roblox asset delivery returned a non-HTTPS location")
    request = urllib.request.Request(location, headers={"Accept-Encoding": "gzip"}, method="GET")
    try:
        with CDN_OPENER.open(request, timeout=60) as response:
            if not 200 <= response.status < 300:
                raise UploadError(f"Roblox CDN returned HTTP {response.status}")
            data = response.read(MAX_UPLOAD_BYTES + 1)
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                data = gzip.decompress(data)
    except urllib.error.HTTPError as error:
        raise HttpFailure(error.code, f"Roblox CDN returned HTTP {error.code}") from error
    except (
        urllib.error.URLError,
        TimeoutError,
        http.client.IncompleteRead,
        gzip.BadGzipFile,
        EOFError,
        zlib.error,
    ) as error:
        raise HttpFailure(None, f"Roblox CDN request failed: {clean_message(error)}") from error
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("Roblox CDN returned an empty or oversized asset")
    parse_png(data, "Delivered texture atlas", EXPECTED_ATLAS_SIZE)
    return data


def wait_for_delivery(
    asset_id: int,
    revision_id: int,
    api_key: str,
    timeout: float,
    poll_interval: float,
):
    deadline = time.monotonic() + timeout
    while True:
        try:
            delivery = fetch_delivery_json(asset_id, revision_id, api_key, deadline)
            errors = delivery.get("errors")
            if errors not in (None, []):
                if delivery_errors_are_transient(errors):
                    raise HttpFailure(404, "Roblox asset delivery is still preparing the texture")
                raise UploadError("Roblox asset delivery returned a terminal error")
            if delivery.get("isArchived") is True:
                raise UploadError("Roblox asset delivery reports the asset as archived")
            location = delivery.get("location")
            if not isinstance(location, str) or not location:
                raise UploadError("Roblox asset delivery did not return a CDN location")
            fetch_cdn_png(location)
            return
        except HttpFailure as error:
            if error.status is not None and error.status not in TRANSIENT_HTTP_CODES | {404}:
                raise
        except UploadError as error:
            if "did not return a CDN location" not in str(error):
                raise
        if time.monotonic() >= deadline:
            raise UploadError(f"Timed out waiting for asset {asset_id} delivery")
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))


def write_recovery_state(image_digest: str, *, operation=None, asset_id=None, revision_id=None):
    state = {"format": 1, "imageSha256": image_digest}
    if operation is not None:
        state["operation"] = f"operations/{operation_id(operation)}"
    if asset_id is not None:
        state["assetId"] = int(asset_id)
    if revision_id is not None:
        state["revisionId"] = int(revision_id)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(f"{STATE_PATH.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(STATE_PATH)


def read_recovery_state(image_digest: str):
    if not STATE_PATH.is_file():
        raise UploadError(f"No upload recovery state exists at {STATE_PATH}")
    try:
        state = json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise UploadError(f"Upload recovery state is unreadable: {STATE_PATH}") from error
    if not isinstance(state, dict) or state.get("format") != 1:
        raise UploadError("Upload recovery state has an unsupported format")
    if state.get("imageSha256") != image_digest:
        raise UploadError("Upload recovery state belongs to a different texture atlas")
    return state


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upload, approve, and verify delivery of the Racer texture atlas."
    )
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the atlas and upload configuration without calling Roblox",
    )
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument(
        "--resume",
        action="store_true",
        help="resume the operation recorded in build/racer-texture-upload-state.json",
    )
    recovery.add_argument(
        "--operation",
        help="resume a known Roblox operation ID or operations/ path",
    )
    recovery.add_argument(
        "--asset-id",
        help="resume moderation and delivery checks for an existing asset ID",
    )
    return parser.parse_args()


def main() -> int:
    os.umask(0o077)
    args = parse_args()
    image_path = args.image.resolve()
    image_data = read_upload(image_path)
    image_digest = hashlib.sha256(image_data).hexdigest()

    api_key = os.environ.get("ROBLOX_API_KEY", "")
    if not api_key:
        raise UploadError("ROBLOX_API_KEY is required")
    group_value = os.environ.get("ROBLOX_CREATOR_GROUP_ID", "")
    user_value = os.environ.get("ROBLOX_CREATOR_USER_ID", "")
    if bool(group_value) == bool(user_value):
        raise UploadError("Set exactly one of ROBLOX_CREATOR_GROUP_ID or ROBLOX_CREATOR_USER_ID")
    creator_key = "groupId" if group_value else "userId"
    creator_id = positive_decimal(group_value or user_value, f"ROBLOX_CREATOR_{creator_key[:-2].upper()}_ID")

    display_name = os.environ.get("ROBLOX_TEXTURE_DISPLAY_NAME", "Racer Sprites v3")
    description = os.environ.get(
        "ROBLOX_TEXTURE_DESCRIPTION", "Production texture atlas for Racer Lab."
    )
    if not display_name.strip():
        raise UploadError("ROBLOX_TEXTURE_DISPLAY_NAME must not be empty")
    if len(description) > 1000:
        raise UploadError("ROBLOX_TEXTURE_DESCRIPTION must be at most 1000 characters")

    operation_timeout = duration_from_env("ROBLOX_ASSET_OPERATION_TIMEOUT_SECONDS", 600)
    moderation_timeout = duration_from_env("ROBLOX_ASSET_MODERATION_TIMEOUT_SECONDS", 7200)
    delivery_timeout = duration_from_env("ROBLOX_ASSET_DELIVERY_TIMEOUT_SECONDS", 900)
    poll_interval = duration_from_env("ROBLOX_ASSET_POLL_INTERVAL_SECONDS", 5)

    if args.validate_only:
        print(f"Validated {image_path} ({len(image_data)} bytes)")
        return 0

    operation = None
    asset_id = None
    if args.resume:
        state = read_recovery_state(image_digest)
        if state.get("assetId") is not None:
            asset_id = normalize_asset_id(state["assetId"], "Recovery assetId")
        elif state.get("operation") is not None:
            operation = {"path": state["operation"], "done": False}
            operation_id(operation)
        else:
            raise UploadError("Upload recovery state has neither an operation nor an asset ID")
    elif args.operation:
        if STATE_PATH.exists():
            raise UploadError(f"Recovery state already exists; use --resume: {STATE_PATH}")
        path = args.operation if args.operation.startswith("operations/") else f"operations/{args.operation}"
        operation = {"path": path, "done": False}
        operation_id(operation)
        write_recovery_state(image_digest, operation=operation)
    elif args.asset_id:
        if STATE_PATH.exists():
            raise UploadError(f"Recovery state already exists; use --resume: {STATE_PATH}")
        asset_id = positive_decimal(args.asset_id, "--asset-id")
        write_recovery_state(image_digest, asset_id=asset_id)
    elif STATE_PATH.exists():
        raise UploadError(f"Previous upload state exists; resume it with --resume: {STATE_PATH}")

    if asset_id is None:
        if operation is None:
            request_json = {
                "assetType": "Image",
                "displayName": display_name,
                "description": description,
                "creationContext": {"creator": {creator_key: creator_id}, "expectedPrice": 0},
            }
            body, content_type = multipart_body(request_json, image_path, image_data)
            print("Submitting Racer texture atlas to Roblox", file=sys.stderr)
            try:
                operation = api_request_json(
                    f"{ASSETS_BASE}/assets",
                    api_key,
                    method="POST",
                    data=body,
                    content_type=content_type,
                )
            except UploadError as error:
                raise UploadError(
                    f"{error}; the POST outcome is ambiguous, so inspect Creator Dashboard before retrying"
                ) from error
            operation_id(operation)
            write_recovery_state(image_digest, operation=operation)
            print(f"Upload recovery state: {STATE_PATH}", file=sys.stderr)
        response = wait_for_operation(operation, api_key, operation_timeout, poll_interval)
        asset_id = normalize_asset_id(response.get("assetId"), "Roblox assetId")
        response_revision = validate_operation_asset(response, asset_id)
        write_recovery_state(
            image_digest,
            operation=operation,
            asset_id=asset_id,
            revision_id=response_revision,
        )
        print(f"Roblox created texture asset {asset_id}", file=sys.stderr)

    revision_id = wait_for_approval(
        asset_id,
        api_key,
        creator_key,
        creator_id,
        moderation_timeout,
        poll_interval,
    )
    write_recovery_state(image_digest, asset_id=asset_id, revision_id=revision_id)
    wait_for_delivery(asset_id, revision_id, api_key, delivery_timeout, poll_interval)
    STATE_PATH.unlink(missing_ok=True)
    print(asset_id)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UploadError as error:
        print(f"Texture upload failed: {clean_message(error)}", file=sys.stderr)
        raise SystemExit(1)
