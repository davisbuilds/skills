from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from urllib import error

import pytest


SCRIPT = Path(__file__).parents[1] / "skills" / "atlas-imagen" / "scripts" / "image_gen.py"
SPEC = importlib.util.spec_from_file_location("atlas_image_gen", SCRIPT)
assert SPEC and SPEC.loader
atlas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(atlas)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def schema():
    return {
        "servers": [{"url": "https://api.atlascloud.ai"}],
        "paths": {
            "/api/v1/model/generateImage": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Input"}
                            }
                        }
                    }
                }
            },
            "/api/v1/model/result/{request_id}": {"get": {}},
        },
        "components": {
            "schemas": {
                "Input": {
                    "type": "object",
                    "required": ["model", "prompt"],
                    "properties": {
                        "model": {"type": "string"},
                        "prompt": {"type": "string"},
                        "size": {"type": "string", "default": "2048*2048"},
                        "enable_base64_output": {"type": "boolean"},
                    },
                }
            }
        },
    }


def test_generate_submits_one_post_and_polls_to_completion():
    calls = []
    responses = iter(
        [
            Response(
                {"data": [{"model": atlas.DEFAULT_MODEL, "schema": "https://schema"}]}
            ),
            Response(schema()),
            Response({"data": {"id": "req-1", "status": "created"}}),
            Response({"data": {"id": "req-1", "status": "processing", "outputs": []}}),
            Response(
                {
                    "data": {
                        "id": "req-1",
                        "status": "completed",
                        "outputs": ["https://image"],
                    }
                }
            ),
        ]
    )

    def opener(req, timeout):
        calls.append((req.method, req.full_url, req.data, dict(req.header_items()), timeout))
        return next(responses)

    output = atlas.generate(
        "a red bicycle",
        model=atlas.DEFAULT_MODEL,
        size=None,
        api_key="secret",
        max_polls=3,
        poll_interval=0,
        opener=opener,
        sleeper=lambda _delay: None,
    )

    assert output == "https://image"
    assert [method for method, *_ in calls].count("POST") == 1
    post = next(call for call in calls if call[0] == "POST")
    payload = json.loads(post[2])
    assert payload == {
        "model": atlas.DEFAULT_MODEL,
        "prompt": "a red bicycle",
        "size": "2048*2048",
        "enable_base64_output": False,
    }
    assert post[3]["User-agent"] == atlas.USER_AGENT
    assert calls[-1][1].endswith("/api/v1/model/result/req-1")


def test_generation_post_is_not_retried():
    methods = []
    responses = iter(
        [
            Response(
                {"data": [{"model": atlas.DEFAULT_MODEL, "schema": "https://schema"}]}
            ),
            Response(schema()),
        ]
    )

    def opener(req, timeout):
        methods.append(req.method)
        if req.method == "POST":
            raise error.HTTPError(req.full_url, 503, "unavailable", {}, io.BytesIO(b"busy"))
        return next(responses)

    with pytest.raises(atlas.AtlasError, match="HTTP 503"):
        atlas.generate(
            "a red bicycle",
            model=atlas.DEFAULT_MODEL,
            size=None,
            api_key="secret",
            max_polls=3,
            poll_interval=0,
            opener=opener,
            sleeper=lambda _delay: None,
        )

    assert methods.count("POST") == 1


def test_polling_stops_at_max_polls():
    responses = iter(
        [
            Response(
                {"data": [{"model": atlas.DEFAULT_MODEL, "schema": "https://schema"}]}
            ),
            Response(schema()),
            Response({"data": {"id": "req-2", "status": "created"}}),
            Response({"data": {"id": "req-2", "status": "processing"}}),
            Response({"data": {"id": "req-2", "status": "processing"}}),
        ]
    )

    with pytest.raises(atlas.AtlasError, match="after 2 result checks"):
        atlas.generate(
            "a red bicycle",
            model=atlas.DEFAULT_MODEL,
            size=None,
            api_key="secret",
            max_polls=2,
            poll_interval=0,
            opener=lambda _req, timeout: next(responses),
            sleeper=lambda _delay: None,
        )


def test_download_retries_get_and_writes_output(tmp_path):
    calls = 0

    def opener(_req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.URLError("temporary")
        return Response(b"image-bytes")

    output = tmp_path / "result.png"
    atlas.download(
        "https://image",
        output,
        opener=opener,
        sleeper=lambda _delay: None,
    )

    assert calls == 2
    assert output.read_bytes() == b"image-bytes"


def test_download_refuses_to_replace_existing_output(tmp_path):
    output = tmp_path / "result.png"
    output.write_bytes(b"keep-me")

    with pytest.raises(atlas.AtlasError, match="already exists"):
        atlas.download("https://image", output, opener=lambda *_args, **_kwargs: None)

    assert output.read_bytes() == b"keep-me"
