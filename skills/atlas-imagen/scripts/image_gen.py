#!/usr/bin/env python3
"""Generate a text-to-image asset through Atlas Cloud."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib import error, request

CATALOG_URL = "https://api.atlascloud.ai/api/v1/models"
DEFAULT_MODEL = "bytedance/seedream-v4"
DEFAULT_OUTPUT = "output/atlas-imagen/image.png"
USER_AGENT = "dojo-atlas-imagen/1.0"
TERMINAL_SUCCESS = {"completed", "succeeded"}
TERMINAL_FAILURE = {"failed", "canceled", "cancelled"}
GET_RETRY_DELAYS = (1.0, 2.0, 4.0)


class AtlasError(RuntimeError):
    """Raised for Atlas Cloud request or response failures."""


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _read_json_response(response: Any) -> Any:
    raw = response.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AtlasError("Atlas Cloud returned invalid JSON") from exc


def _http_error(exc: error.HTTPError) -> AtlasError:
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
    except Exception:
        detail = ""
    suffix = f": {detail}" if detail else ""
    return AtlasError(f"Atlas Cloud HTTP {exc.code}{suffix}")


def _json_request(
    method: str,
    url: str,
    *,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
    opener: Callable[..., Any] = request.urlopen,
) -> Any:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    body = None
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener(req, timeout=60) as response:
            return _read_json_response(response)
    except error.HTTPError as exc:
        raise _http_error(exc) from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise AtlasError(f"Atlas Cloud {method} failed: {exc}") from exc


def _get_json(
    url: str,
    *,
    api_key: str | None = None,
    opener: Callable[..., Any] = request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    last_error: AtlasError | None = None
    for attempt in range(len(GET_RETRY_DELAYS) + 1):
        try:
            return _json_request("GET", url, api_key=api_key, opener=opener)
        except AtlasError as exc:
            last_error = exc
            if attempt == len(GET_RETRY_DELAYS):
                break
            sleeper(GET_RETRY_DELAYS[attempt])
    assert last_error is not None
    raise last_error


def _post_json_once(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    opener: Callable[..., Any] = request.urlopen,
) -> Any:
    return _json_request(
        "POST", url, api_key=api_key, payload=payload, opener=opener
    )


def _model_schema(
    model: str,
    *,
    opener: Callable[..., Any] = request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    catalog = _unwrap(_get_json(CATALOG_URL, opener=opener, sleeper=sleeper))
    if not isinstance(catalog, list):
        raise AtlasError("Atlas Cloud model catalog has an unexpected shape")
    match = next(
        (item for item in catalog if isinstance(item, dict) and item.get("model") == model),
        None,
    )
    if match is None:
        raise AtlasError(f"Model not found in the Atlas Cloud catalog: {model}")
    schema_url = match.get("schema")
    if not isinstance(schema_url, str) or not schema_url:
        raise AtlasError(f"Model has no schema URL: {model}")
    schema = _get_json(schema_url, opener=opener, sleeper=sleeper)
    if not isinstance(schema, dict):
        raise AtlasError(f"Model schema has an unexpected shape: {model}")
    return schema


def _operation(schema: dict[str, Any], method: str) -> tuple[str, dict[str, Any]]:
    method = method.lower()
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise AtlasError("Model schema does not define API paths")
    for path, methods in paths.items():
        if isinstance(methods, dict) and method in methods:
            return str(path), methods[method]
    raise AtlasError(f"Model schema does not define a {method.upper()} operation")


def _input_schema(schema: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    body_schema = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = body_schema.get("$ref") if isinstance(body_schema, dict) else None
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        raise AtlasError("Model schema does not expose a JSON input definition")
    name = ref.rsplit("/", 1)[-1]
    value = schema.get("components", {}).get("schemas", {}).get(name)
    if not isinstance(value, dict):
        raise AtlasError("Model schema input reference cannot be resolved")
    return value


def _build_payload(
    schema: dict[str, Any], model: str, prompt: str, size: str | None
) -> tuple[str, str, dict[str, Any]]:
    post_path, post_operation = _operation(schema, "post")
    result_path, _ = _operation(schema, "get")
    input_schema = _input_schema(schema, post_operation)
    properties = input_schema.get("properties", {})
    if not isinstance(properties, dict):
        raise AtlasError("Model input properties are invalid")

    payload: dict[str, Any] = {"model": model, "prompt": prompt}
    if size is not None:
        if "size" not in properties:
            raise AtlasError(f"The selected model does not accept size: {model}")
        payload["size"] = size
    elif isinstance(properties.get("size"), dict) and "default" in properties["size"]:
        payload["size"] = properties["size"]["default"]
    if "enable_base64_output" in properties:
        payload["enable_base64_output"] = False

    unknown = set(payload) - set(properties)
    if unknown:
        raise AtlasError(f"Payload fields are absent from live schema: {sorted(unknown)}")
    missing = set(input_schema.get("required", [])) - set(payload)
    if missing:
        raise AtlasError(f"Missing required payload fields: {sorted(missing)}")
    return post_path, result_path, payload


def _base_url(schema: dict[str, Any]) -> str:
    servers = schema.get("servers")
    if not isinstance(servers, list) or not servers:
        raise AtlasError("Model schema does not define an API server")
    url = servers[0].get("url") if isinstance(servers[0], dict) else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise AtlasError("Model schema API server is invalid")
    return url.rstrip("/")


def _prediction(payload: Any) -> dict[str, Any]:
    value = _unwrap(payload)
    if not isinstance(value, dict):
        raise AtlasError("Atlas Cloud prediction response has an unexpected shape")
    return value


def _outputs(prediction: dict[str, Any]) -> list[str]:
    outputs = prediction.get("outputs") or prediction.get("output") or []
    if isinstance(outputs, str):
        outputs = [outputs]
    return [item for item in outputs if isinstance(item, str) and item]


def generate(
    prompt: str,
    *,
    model: str,
    size: str | None,
    api_key: str,
    max_polls: int,
    poll_interval: float,
    opener: Callable[..., Any] = request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    schema = _model_schema(model, opener=opener, sleeper=sleeper)
    post_path, result_path, payload = _build_payload(schema, model, prompt, size)
    base_url = _base_url(schema)

    submitted = _prediction(
        _post_json_once(
            base_url + post_path, api_key=api_key, payload=payload, opener=opener
        )
    )
    status = str(submitted.get("status", "")).lower()
    outputs = _outputs(submitted)
    if status in TERMINAL_SUCCESS and outputs:
        return outputs[0]
    if status in TERMINAL_FAILURE:
        raise AtlasError(f"Generation failed with status: {status}")

    request_id = submitted.get("id") or submitted.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise AtlasError("Generation response did not include a request ID")

    result_url = base_url + result_path.replace("{request_id}", request_id)
    delay = poll_interval
    for _ in range(max_polls):
        sleeper(delay)
        result = _prediction(
            _get_json(result_url, api_key=api_key, opener=opener, sleeper=sleeper)
        )
        status = str(result.get("status", "")).lower()
        outputs = _outputs(result)
        if status in TERMINAL_SUCCESS:
            if not outputs:
                raise AtlasError("Generation completed without an output URL")
            return outputs[0]
        if status in TERMINAL_FAILURE:
            raise AtlasError(f"Generation failed with status: {status}")
        delay = min(delay * 1.5, 10.0)
    raise AtlasError(f"Generation did not finish after {max_polls} result checks")


def download(
    url: str,
    output: Path,
    *,
    force: bool = False,
    opener: Callable[..., Any] = request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    if output.exists() and not force:
        raise AtlasError(f"Output already exists: {output} (use --force to replace it)")
    last_error: Exception | None = None
    for attempt in range(len(GET_RETRY_DELAYS) + 1):
        try:
            req = request.Request(
                url,
                headers={"Accept": "image/*", "User-Agent": USER_AGENT},
                method="GET",
            )
            with opener(req, timeout=120) as response:
                content = response.read()
            if not content:
                raise AtlasError("Generated image download was empty")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            return
        except (AtlasError, error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == len(GET_RETRY_DELAYS):
                break
            sleeper(GET_RETRY_DELAYS[attempt])
    raise AtlasError(f"Could not download generated image: {last_error}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Text-to-image prompt")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Atlas Cloud model ID")
    parser.add_argument("--size", help="Model-supported image size")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Output image path")
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    args.prompt = args.prompt.strip()
    if not args.prompt:
        raise AtlasError("--prompt cannot be empty")
    if args.max_polls < 1:
        raise AtlasError("--max-polls must be at least 1")
    if args.poll_interval < 0:
        raise AtlasError("--poll-interval cannot be negative")
    if args.dry_run:
        schema = _model_schema(args.model)
        _, _, payload = _build_payload(schema, args.model, args.prompt, args.size)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    api_key = os.environ.get("ATLASCLOUD_API_KEY")
    if not api_key:
        raise AtlasError("ATLASCLOUD_API_KEY is not set")
    output = Path(args.out)
    output_url = generate(
        args.prompt,
        model=args.model,
        size=args.size,
        api_key=api_key,
        max_polls=args.max_polls,
        poll_interval=args.poll_interval,
    )
    download(output_url, output, force=args.force)
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AtlasError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
