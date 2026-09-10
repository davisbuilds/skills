# Dojo

This repository contains **Agent Skills**: markdown-first packages that extend AI agents with specialized knowledge, workflows, and tool integrations. Skills are agent-agnostic by default, with lifecycle hooks and a generated manifest keeping the catalog usable across Claude Code, Codex, and similar harnesses.

## Agent Setup

New here? Paste the prompt below into your coding agent (Claude Code, Codex, etc.) and it will install the toolchain, validate the skills, and tell you how to install a skill into your agent.

```text
Set up the `dojo` repo for me. It's a collection of agent-agnostic Skills (markdown
`SKILL.md` files) and lifecycle hooks for coding agents like Claude Code and Codex.
It's markdown-first with small Python helper scripts.

Do this, in order:

1. Check system tools. These must be on PATH (the hooks use them): git, jq,
   python3, sed, grep. Run:
   for cmd in git jq python3 sed grep; do command -v "$cmd" >/dev/null && echo "$cmd: ok" || echo "$cmd: MISSING"; done
   If any are MISSING, tell me which and how to install (e.g. `brew install jq`).

2. Install Python deps from the hash-pinned lockfile:
   `python3 -m pip install --require-hashes -r requirements.lock` (currently just
   PyYAML). No env vars or secrets are required for the core repo — only the
   optional atlas-imagen / gpt-imagen / gemini-imagen skills need
   ATLASCLOUD_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY,
   and only if I use them.

3. Verify WITHOUT any secrets: run the skill-contract validator —
   `python3 skills/skill-evals/scripts/validate_skill_contract.py --skills-root skills --strict`.
   It should pass. If it fails, show me the output and stop.

4. Apply harness adapters so this repo's skills are discoverable by SKILL.md-native
   harnesses: `python3 scripts/gen_harness_adapters.py`. This creates local,
   gitignored symlinks (`.claude/skills`, `.agent/skills` -> `../skills`) and
   leaves the committed Codex sidecars untouched — it produces no
   git changes. (Codex sidecars at `skills/<name>/agents/openai.yaml` are already
   committed, so Codex works without this step.)

5. Report back: confirm tools present + deps installed + validator passed, and show
   me how to install a skill into my agent, e.g.
   `python3 skills/skill-installer/scripts/install-skill-from-github.py --agent claude --repo davisbuilds/dojo --path skills/<skill-name>`.

Don't commit anything.
```

Prefer to do it yourself? The manual steps are below.

## Documentation

- **Agent guidance**: [`AGENTS.md`](AGENTS.md)
- **Architecture and skill structure**: [`docs/system/ARCHITECTURE.md`](docs/system/ARCHITECTURE.md)
- **Skill catalog and command wrappers**: [`docs/system/FEATURES.md`](docs/system/FEATURES.md)
- **Setup and operations**: [`docs/system/OPERATIONS.md`](docs/system/OPERATIONS.md)
- **Skill authoring guidance**: [`docs/system/SKILL-BEST-PRACTICES.md`](docs/system/SKILL-BEST-PRACTICES.md)
- **Strict skill contract**: [`docs/system/skill-contract-v1.md`](docs/system/skill-contract-v1.md)
- **Vision, roadmap, and backlog**: [`docs/project/VISION.md`](docs/project/VISION.md), [`docs/project/ROADMAP.md`](docs/project/ROADMAP.md), [`docs/project/BACKLOG.md`](docs/project/BACKLOG.md)
- **Git history policy**: [`docs/project/GIT_HISTORY_POLICY.md`](docs/project/GIT_HISTORY_POLICY.md)

The generated [`skills.json`](skills.json) manifest is the runtime inventory source of truth.

## Prerequisites

The hooks require `git`, `jq`, `python3`, `sed`, and `grep`. These ship with most systems. Verify with:

```bash
for cmd in git jq python3 sed grep; do command -v "$cmd" >/dev/null && echo "$cmd: ok" || echo "$cmd: MISSING"; done
```

If everything prints `ok`, install the Python dependencies. Otherwise install the missing tool(s) via your package manager, for example `brew install jq`.

## Install

Install the core Python dependencies from the hash-pinned lockfile:

```bash
python3 -m pip install --require-hashes -r requirements.lock
```

`requirements.txt` is the human-edited source for the lock. When the dependency set changes, regenerate [`requirements.lock`](requirements.lock) with:

```bash
uv pip compile --generate-hashes requirements.txt -o requirements.lock
```

Some skills bundle optional dependencies:

| Skill | Extra packages | Env vars |
|-------|----------------|----------|
| `skills/atlas-imagen/` | None (Python standard library only) | `ATLASCLOUD_API_KEY` |
| `skills/gpt-imagen/` | `openai>=1.0.0`, `Pillow>=10.0.0` | `OPENAI_API_KEY` |
| `skills/gemini-imagen/` | `google-genai>=1.0.0`, `Pillow>=10.0.0` | `GEMINI_API_KEY` |
| `skills/design-md/` | `npx` on PATH; pulls `@google/design.md@0.1.1` on first invocation | — |

## Quick Start

```bash
# Validate the full skill catalog against the strict contract.
python3 skills/skill-evals/scripts/validate_skill_contract.py --skills-root skills --strict

# Inspect the runtime skill count.
jq '.skills | length' skills.json

# Regenerate the manifest after skill metadata changes.
python3 scripts/generate_skills_manifest.py

# Install a skill into an agent.
python3 skills/skill-installer/scripts/install-skill-from-github.py \
  --agent claude \
  --repo davisbuilds/dojo \
  --path skills/<skill-name>
```

## Skill Model

A skill is a self-contained directory that provides:

- **Instructions**: task-specific guidance in `SKILL.md`.
- **Context**: specialized references or best practices.
- **Workflow**: a structured approach to complex problems.

Each skill follows this structure:

```
skill-name/
├── SKILL.md           # Required: Frontmatter (YAML) + Instructions (Markdown)
├── commands/          # Optional: command-wrapper docs for slash-style entrypoints
├── scripts/           # Optional: Executable scripts (Python/Bash)
├── references/        # Optional: Documentation files
└── assets/            # Optional: Templates, images, or other assets
```

The `SKILL.md` file contains the "brain" of the skill—the prompt instructions that are loaded into the agent's context when the skill is triggered.

`SKILL.md` frontmatter declares a per-skill SemVer `version` used by `skills.json`, the catalog, and release-bump checks. New stable skills start at `1.0.0`.

`SKILL.md` frontmatter should also declare a `skill-type` for new or updated skills:
- `workflow` for procedural, review, audit, remediation, or planning skills
- `reference` for best-practice indexes and reference routers

Context loading follows progressive disclosure: manifest metadata is always available, `SKILL.md` loads only when triggered, and bundled resources are read on demand.

Skills may also declare an optional `triggers:` list of literal trigger phrases. These are machine-checkable by the trigger evals (`run_trigger_evals.py --from-triggers`) and stay optional — absence changes nothing.

### Multi-harness support

The agent-agnostic claim is backed by generated adapters, not duplicated content. `scripts/gen_harness_adapters.py` derives, from each skill's frontmatter:

- **Dir-level relative symlinks** so SKILL.md-native harnesses see every skill: `.claude/skills` and `.agent/skills` each point to `../skills`. These live under gitignored harness dirs, so they are **local-only and regenerated per clone** — run the generator after cloning. `.agents/skills` is **deliberately not created, and actively retired if found**: Codex reads it as project scope and does not shadow by name, so it listed the whole catalog a second time (measured 90 entries against 41, 80 of them truncated). Because the link is gitignored, pulling this change cannot remove it — the generator does.
- **A colocated Codex sidecar** at `skills/<name>/agents/openai.yaml`. These are committed, portable artifacts. Generated sidecars carry an `AUTO-GENERATED` marker; hand-curated ones (with icons, polished copy) are preserved and never overwritten.
- **Slash-command links** from each skill's `commands/*.md` into `.claude/commands/` so Claude Code resolves them as real slash commands (`/review`, `/quiz-change`, `/workflows:brainstorm`). Local-only and gitignored, like the skill symlinks.

Run `python3 scripts/gen_harness_adapters.py` to regenerate everything locally. CI enforces the committed sidecars with `gen_harness_adapters.py --check --skip-symlinks`.

## Available Skills

Skills span GitHub workflows, code review, content creation, dev workflows, platform integrations, knowledge management, and meta/skill tooling. Use `jq '.skills | length' skills.json` for the current runtime count, and see [docs/system/FEATURES.md](docs/system/FEATURES.md) for the catalog snapshot.

For a searchable view, open [`docs/catalog/index.html`](docs/catalog/index.html) — a self-contained page generated from `skills.json` by `scripts/gen_catalog.py` (rebuilt automatically when skill metadata changes).

## Hooks

Hooks in `hooks/` enforce skill quality, inject session context, and nudge agents to capture learnings (skill catalog, frontmatter validation, manifest regeneration, git checks, structure checks, session retro reminder). Configured in `.claude/settings.json` and `.agents/settings.json`. See [docs/system/ARCHITECTURE.md](docs/system/ARCHITECTURE.md) for details.

## Creating and Shipping Skills

You can use the `skill-creator` scripts to scaffold a new skill:

```bash
# Create a new skill directory
python3 skills/skill-creator/scripts/init_skill.py <skill-name> --path ./ \
  --resources scripts,references --examples

# Validate your skill structure (works with both `python` and `python3`)
python3 skills/skill-creator/scripts/quick_validate.py <skill-name>

# Package a skill for distribution
python3 skills/skill-creator/scripts/package_skill.py <skill-name> ./dist

# Optional: generate OpenAI/Codex metadata add-on
python3 skills/skill-creator/scripts/generate_openai_yaml.py <skill-name> \
  --interface default_prompt="Use $<skill-name> to help with this task."
```

The validator uses a polyglot shebang so it can also be run directly and will work in environments that provide either `python` or `python3`.

For new or updated skills, set `skill-type` before validating so the contract enforces the right structure.

## Agent Usage

When working with an agent that supports these skills:

1. **Trigger**: The agent will select a skill based on its `description` in `SKILL.md` when it matches your request.
2. **Follow Instructions**: The agent will then follow the specific protocols defined in the skill's body.
3. **Tools**: Some skills may require specific tools (like `gh` CLI or `python`) to be installed in your environment.

### Skill Installer Targets

`skills/skill-installer` supports both Codex and Claude Code destinations:

```bash
# Install to Claude Code skills (~/.claude/skills by default)
python3 skills/skill-installer/scripts/install-skill-from-github.py \
  --agent claude \
  --repo openai/skills \
  --path skills/.curated/create-cli
```

### Command Wrappers

Some skills include optional `commands/*.md` wrappers for slash-style entrypoints. See [docs/system/FEATURES.md](docs/system/FEATURES.md) for the full list.

## Code Layout

```text
skills/                   skill directories; each skill is anchored by SKILL.md
hooks/                    lifecycle hooks for validation, manifest updates, and session checks
scripts/                  manifest generation and helper scripts
tests/                    regression tests for repository scripts
spec/                     agent skills specification
docs/system/              architecture, operations, catalog, contract, and authoring references
docs/project/             project vision, backlog, and git history policy
docs/design/              brainstorm design summaries (WHAT — chosen direction)
docs/specs/               contracts (WHAT must be true — falsifiable target)
docs/plans/               implementation plans (HOW — task sequencing)
docs/downloads/           pre-packaged .skill files
docs/archive/             historical analyses and completed plans
```

## Current Boundaries

- `skills.json` is generated from `skills/*/SKILL.md`; do not hand-edit it as the primary source.
- Hooks are configured for supported local harnesses, but CI currently enforces the strict skill contract only.
- Optional image and design skills can require external CLIs or API keys; the core repo validation does not.
- `commands/*.md` wrappers are part of the skill surface even when a harness does not expose command files.

## Acknowledgements

- [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [superpowers](https://github.com/obra/superpowers)
- [agent-scripts](https://github.com/steipete/agent-scripts)
- [anthropics/skills](https://github.com/anthropics/skills)
- [compound-engineering-plugin](https://github.com/everyinc/compound-engineering-plugin) — source of the agent-native-architecture and compound-docs skills
- [Vercel skills](https://github.com/vercel/next.js) — React, Next.js, React Native best-practice rules and composition patterns, plus preview deployment debugging workflows
- [Kepano's Obsidian skills](https://github.com/kepano) — Obsidian Markdown, Bases, and JSON Canvas skill references
- [skills.sh](https://skills.sh) — community skill registry and discovery
- [Google Labs `@google/design.md`](https://github.com/google-labs-code/design.md) — DESIGN.md format and CLI wrapped by the `design-md` skill (Apache-2.0)
- [Refero](https://styles.refero.design) — source of the five DESIGN.md exemplars vendored under `skills/design-md/references/exemplars/`
- [impeccable.style](https://impeccable.style/slop) — slop anti-pattern taxonomy paraphrased into the `design-critique` slop catalog
- [mattpocock/skills](https://github.com/mattpocock/skills) — source of the `diagnose` (feedback-loop-first debugging) and `caveman` (ultra-compressed communication mode) skills (MIT)
