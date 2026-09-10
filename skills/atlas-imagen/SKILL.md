---
name: "atlas-imagen"
description: "Generate images through Atlas Cloud with live model-schema validation and bounded result polling. Use when the user asks for text-to-image assets with Atlas Cloud or has ATLASCLOUD_API_KEY configured."
skill-type: workflow
compatibility: "Requires python3, network access, and ATLASCLOUD_API_KEY for live generation. The bundled CLI uses only the Python standard library."
version: 1.0.0
---

# Atlas Imagen

Generate text-to-image assets through Atlas Cloud with the bundled CLI. The CLI discovers the selected model's current OpenAPI schema before constructing a request, submits exactly one generation POST, and uses bounded GET polling for the result.

## Scope

Use this skill for Atlas Cloud text-to-image generation. Do not claim image editing, image-to-image, or parameters that are absent from the selected model's live schema.

## Boundaries

- Require explicit user intent before a live generation because it may be billable.
- Never retry the generation POST. A retry can create a duplicate billable task.
- Retry only catalog, schema, result, and output GET requests, with bounded backoff.
- Never print, store, or request the full `ATLASCLOUD_API_KEY` in chat.
- Do not invent model IDs or request fields. The CLI validates them against the live model catalog and schema.

## Workflow

1. Confirm the requested subject, intended use, composition, style, and constraints. Keep unprovided creative choices provisional.
2. Confirm that `ATLASCLOUD_API_KEY` is set locally.
3. Preview the exact payload. This performs read-only catalog and schema GET requests, but does not submit a generation:

   ```bash
   python3 <skill-dir>/scripts/image_gen.py \
     --prompt "A restrained studio product photo of a ceramic mug" \
     --size '2048*2048' \
     --out output/atlas-imagen/mug.png \
     --dry-run
   ```

4. Obtain confirmation before the potentially billable call, then run the same command without `--dry-run`.
5. Inspect the saved image for prompt fidelity, composition, text accuracy, and requested constraints. Make only targeted prompt changes before another explicitly approved generation.

## CLI

```bash
python3 <skill-dir>/scripts/image_gen.py \
  --prompt "Editorial photograph of a red bicycle against a white wall" \
  --out output/atlas-imagen/bicycle.png
```

Options:

- `--model`: Atlas Cloud model ID. Defaults to `bytedance/seedream-v4`.
- `--size`: Image size accepted by the selected model's live schema. Defaults to the schema value.
- `--out`: Destination image path.
- `--max-polls`: Maximum result checks. Defaults to 60.
- `--poll-interval`: Initial seconds between result checks. Defaults to 2.
- `--force`: Allow replacing an existing output file.
- `--dry-run`: Read the live schema and print the exact payload without submitting a generation.

## Output Contract

- Save one generated image to the requested `--out` path.
- Print the output path only after the download succeeds.
- On failure, exit nonzero with the API status or bounded polling error.
- Preserve the final prompt, model ID, size, and output path in the calling task's report.

## Verification

- The model exists in the live Atlas Cloud catalog.
- The request payload contains only fields exposed by the live model schema.
- Exactly one generation POST was sent.
- Polling stopped on `completed`/`succeeded`, a terminal failure, or `--max-polls`.
- The output file exists and is non-empty.

## Resource Map

- **`scripts/image_gen.py`**: schema-aware Atlas Cloud generation, bounded polling, and output download CLI.

## Sibling Skills

- `gpt-imagen`: choose when the user explicitly requests OpenAI image generation or editing.
- `gemini-imagen`: choose when the user explicitly requests Gemini image generation, editing, or composition.
