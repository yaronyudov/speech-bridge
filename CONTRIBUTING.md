# Contributing to speech-bridge

Thanks for helping improve speech-bridge! This guide covers local setup and
the quality gates CI enforces.

## Local setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate
make install          # runtime + dev dependencies
pre-commit install    # optional: run linters/formatters on commit
```

## Quality gates

CI runs these on every PR; run them locally first:

```bash
make lint        # ruff check
make fmt         # ruff format + autofix
make typecheck   # mypy speech_engine
make test        # pytest
make check       # all of the above

# Terraform (if you touched infra/)
make tf-fmt
make tf-validate
```

The pytest suite runs fully offline — heavy ML models and edge-tts are stubbed
(see `tests/conftest.py`), so no GPU, network, or cloud credentials are needed.

## Conventions

- **Python**: 3.11+, formatted by `ruff format` (88 cols). Keep provider SDK
  imports **lazy** (inside methods) so optional engines don't become hard
  dependencies — mirror the pattern in `core/stt/remote.py`.
- **New engines**: implement the `BaseSTTEngine` / `BaseTTSEngine` interface,
  register in the relevant factory, add language/voice mappings to
  `core/constants.py`, and raise `ConfigurationError` with an actionable
  message when a package or credential is missing.
- **New settings**: add to `config.py`, document in `.env.example` +
  `config.yaml.example`, and reference in the README.
- **Terraform**: keep every sub-resource optional (`create_*` flag +
  `existing_*` passthrough); run `terraform fmt` before committing.
- **Tests**: add coverage for new endpoints/branches; prefer the offline
  `TestClient` + stub approach.

## Pull requests

Fill in the PR template, ensure the checklist passes, and keep changes
focused. See `docs/PRODUCTION.md` for the roadmap of larger initiatives.
