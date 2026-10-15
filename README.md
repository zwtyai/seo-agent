# seo-agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Pages](https://img.shields.io/badge/demo-GitHub%20Pages-222?logo=github)](https://zwtyai.github.io/seo-agent/)

**Automated SEO content factory** built with [CrewAI](https://www.crewai.com/) and **Vertex AI Gemini**.  
It researches real search pain points (Google Search Grounding), drafts a short article, runs SEO checks, and publishes static HTML for GitHub Pages.

> 中文简介：用多智能体自动「挖词 → 写稿 → 质检 → 静态发布」的 SEO 流水线，适合作为可复用的开源范例；示例站点面向 [yibelin.com](https://yibelin.com)（PDF 在线翻译）场景。

**Live demo:** https://zwtyai.github.io/seo-agent/

---

## What it does

| Step | Agent / component | Job |
|------|-------------------|-----|
| 1 | Keyword Researcher | Vertex Gemini + **Google Search Grounding** finds one long-tail pain point with real URLs |
| 2 | Content Writer | Writes a short Markdown draft using a product knowledge tool |
| 3 | SEO Editor | Density / structure check + inject absolute internal links |
| 4 | `static_publish.py` | Writes HTML/Markdown under `docs/` for GitHub Pages |
| 5 | GitHub Actions | Scheduled or manual run; opens a PR to update `docs/` |

```text
seed keyword
    → Grounding research (1 brief)
    → short Markdown draft (~200 words in dry-run mode)
    → SEO link pass
    → docs/posts/*.html + docs/index.html
    → PR → merge → Pages (or later Vercel, etc.)
```

---

## Features

- **Vertex AI Gemini** (`gemini-2.5-flash` by default), same credential style as many GCP / doc2doc setups
- **Native Google Search Grounding** for research (no Custom Search API key required)
- **Static site output** in `docs/` — works with classic GitHub Pages (`main` + `/docs`)
- **GitHub Actions** cron + `workflow_dispatch`; `main` is **PR-only**
- Optional WordPress / Search Console helpers in `publish_and_monitor.py` (not required for Pages)

---

## Requirements

- Python **3.10–3.13** (CrewAI does not support 3.14 yet)
- A GCP project with **Vertex AI** enabled and a service account that can call Gemini
- GitHub repository secrets if you run the Actions workflow

---

## Quick start (local)

```bash
git clone https://github.com/zwtyai/seo-agent.git
cd seo-agent
python3.10 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — never commit real secrets
python main.py
```

Generated pages land in `docs/`. Open `docs/index.html` locally, or push via PR and use GitHub Pages.

### Required environment variables

See [`.env.example`](.env.example). Minimum for a local run:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CREDENTIALS_ENC` + `DOC2DOC_SECRETS_KEY` | Encrypted service-account JSON + passphrase (**recommended**) |
| *or* `GOOGLE_APPLICATION_CREDENTIALS` | Path to a local service-account JSON file |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | e.g. `us-central1` (optional default) |
| `GEMINI_MODEL` | e.g. `gemini-2.5-flash` (optional default) |

Also recommended:

```bash
OTEL_SDK_DISABLED=true
CREWAI_DISABLE_TELEMETRY=true
```

---

## GitHub Actions automation

Workflow: [`.github/workflows/seo_factory.yml`](.github/workflows/seo_factory.yml)

1. Add the same keys as **Actions secrets** (Settings → Secrets and variables → Actions).
2. Run **Actions → Yibelin SEO Automation Factory → Run workflow**, or wait for the cron schedule.
3. The job opens a PR that updates `docs/`; merge it to refresh Pages.

`main` is protected: **all changes (including generated docs) go through pull requests.**

If the workflow fails with `GitHub Actions is not permitted to create or approve pull requests`:

1. **Org setting (preferred):** Organization → Settings → Actions → General → Workflow permissions → enable **Read and write permissions** and **Allow GitHub Actions to create and approve pull requests**.
2. **Or** add a secret `GH_PAT` (classic PAT with `repo`, or fine-grained with Contents + Pull requests on this repo). The workflow uses `GH_PAT` when present.

---

## Repository layout

```text
main.py                 # CrewAI agents, tasks, kickoff
vertex_llm.py           # Vertex credentials + Search Grounding patch
static_publish.py       # Markdown → docs/ HTML
publish_and_monitor.py  # Optional WordPress / GSC helpers
docs/                   # GitHub Pages site
.github/workflows/      # Scheduled SEO factory
```

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md).

- Do **not** commit `.env`, service-account JSON, or API keys
- Open a **pull request** against `main` (direct pushes are blocked)
- Keep changes focused and documented

## Security

Please see [SECURITY.md](SECURITY.md) for how to report vulnerabilities or leaked credentials.

## License

This project is released under the [MIT License](LICENSE).

## Acknowledgments

- [CrewAI](https://github.com/crewAIInc/crewAI)
- [Google Vertex AI / Gemini](https://cloud.google.com/vertex-ai)
- Demo content theme: [yibelin.com](https://yibelin.com)
