# wildbreeze — the commercial site at www.wildbreeze.io

Static HTML site published to GitHub Pages. Bilingual (EN at root, ES under `/es/`), with a password-gated client portal under `/account/`.

## Repo + deploy

- **Source repo:** `jackmichaelnapier/personal` on GitHub, path `wildbreeze/`
- **Local working copy:** this folder (`~/Projects/wildbreeze/`)
- **Deploy script:** `_publish.py` (uses GitHub Contents API, token from `NAPIER_PUBLISH_TOKEN` or macOS Keychain `napier-publish-token`)
- **Deploy a single page:** `python3 _publish.py <relative-path>`
- **Deploy everything:** `python3 _publish_all.py`

## Where things are

| Path | What |
|------|------|
| `index.html` | EN homepage |
| `es/` | Spanish mirror |
| `account/` | Encrypted client portal — gate at `account/index.html`, per-client folders under `account/clients/<slug>/` |
| `field-guide/` | Auto-publishing article tree |
| `mia/`, `vs/`, `glossary/`, `calculator/`, `about/`, `contact/`, `dev-brief/`, `products/` | Marketing pages |
| `wb-style.css` | Shared stylesheet |
| `media/` | Images and assets |
| `_*.py` | Build/publish scripts (prefixed with `_` so they sort to the top) |
| `_wb_encrypt.py` | Encryption library for the client gate (PBKDF2 + AES-GCM) |
| `_clients.py` | Manages per-client credentials from `~/.claude/wildbreeze/clients.json` |
| `_inject_header.py`, `_inject_tags.py` | Site-wide element injection (header, tracking tags, footer pills) |
| `11pm-audit/` | Old audit dump, treat as archive |
| `account/`, portal-related scripts (`_account_setup.py`, `_wildbreeze_account*.py`, `_portal_updated*.html`, `_preview_cs_*.html`) | Client-portal scaffolding and preview snapshots |

## Conventions

- Anything that should appear on every page is injected via marker fences. See the `wildbreeze-tags` and `wildbreeze-header` skills.
- Before pushing, ALWAYS use the `github-safe-push` pattern (the repo has parallel writers).
- The client area is encrypt-at-rest. See `wildbreeze-client-area` and `encrypted-gate-page` skills.
- Visual design rules live in the `wildbreeze-design` skill.

## Reports published into the client portal

- Pricemart finance weekly → `account/clients/pricemart-finance/`  (skill: `weekly-pricemart-finance-report`)
- Sweden weekly → `account/clients/pricemart-finance/`  (skill: `weekly-sweden-report`)
- Pricemart purchasing watchtower → `account/clients/pricemart-purchasing/`  (skill: `weekly-pricemart-purchasing-watchtower`)

## Wiki (compounding domain knowledge)

`wiki/` is the WildBreeze business knowledge base. Skills tell us *how to build site things*; the wiki tells us *what we know about the business, the clients, and the playbooks*.

- `wiki/index.md`. Catalog. Read first by `wiki-query`.
- `wiki/entities/`. Clients, prospects, partners, vendors, key people.
- `wiki/concepts/`. Methodologies (quiet-automation playbook, client onboarding, MCP recipes, pricing patterns).
- `wiki/sources/`. One dated summary per ingested source (meeting transcripts, sales conversations, customer feedback, competitor pages).
- `wiki/README.md`. The conventions in full.

Operations:
- `/wiki-ingest <source>`. File a new source.
- `/wiki-query <question>`. Answer from the wiki, cited.
- `/wiki-lint`. Monthly health check. Scheduled.

The wiki does not store: live site code, visual rules (those are skills), credentials, or anything that lives in the repo as published content.

## Don't

- Don't link `go.napier.me` URLs from any public page (confidential, see MEMORY.md).
- Don't mention "FitnessNord" or "Welzyn S.L." on `napier.me` personal pages (also in MEMORY.md).
- Don't put client credentials or access keys in the wiki. Those live in `~/.claude/wildbreeze/clients.json`.
