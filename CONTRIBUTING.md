# Contributing to seo-agent

Thanks for helping improve this project.

## Ground rules

1. **Pull requests only** — `main` is protected; do not push commits directly to `main`.
2. **Never commit secrets** — `.env`, service-account JSON, API keys, or encrypted blobs with real keys stay local / in GitHub Actions secrets.
3. Prefer small, focused PRs with a clear description of *why*.

## Development setup

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in your own Vertex credentials
python main.py
```

Use your own GCP project. Do not ask maintainers for production credentials.

## Pull request checklist

- [ ] Branch from latest `main`
- [ ] No secrets or credential files in the diff
- [ ] `python main.py` still runs locally if you touched the pipeline
- [ ] Update `.env.example` / README if you add env vars
- [ ] PR description explains the change and how you tested it

## Issue reports

Use GitHub Issues. Include:

- What you expected vs what happened
- Python version and OS
- Relevant logs with secrets redacted

## Code of conduct

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).
