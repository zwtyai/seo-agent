# Security Policy

## Supported versions

This repository is under active development. Security fixes are applied on the latest `main` branch.

## Reporting a vulnerability

If you discover a security issue (including accidentally exposed keys in issues, PRs, or Actions logs):

1. **Do not** open a public GitHub Issue with secrets or exploit details.
2. Email the maintainers via the contact listed on the [GitHub organization](https://github.com/zwtyai) profile, or use GitHub’s **Private vulnerability reporting** if enabled for this repository (Security → Advise a vulnerability).
3. Include steps to reproduce and impact assessment when possible.

We will acknowledge the report when possible and coordinate a fix before any public disclosure.

## Secrets hygiene

- Keep credentials in local `.env` or GitHub Actions secrets only.
- Rotate any key that may have been committed or pasted into chat/logs.
- Prefer encrypted service-account material (`GOOGLE_CREDENTIALS_ENC` + passphrase) over committing JSON files.
