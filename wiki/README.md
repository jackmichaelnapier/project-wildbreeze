# wildbreeze wiki

Compounding knowledge base for the WildBreeze business and the operations behind www.wildbreeze.io. Karpathy's LLM-wiki pattern.

## What lives here

```
wiki/
  index.md       # catalog of all pages, read first by wiki-query
  README.md      # this file
  entities/      # one page per real-world thing
  concepts/      # one page per methodology, framework, recurring pattern
  sources/       # summary page per ingested source, dated
```

## What goes where

**Entities** — proper nouns. Clients (Pricemart and the two team variants: pricemart-finance, pricemart-purchasing), prospects, partners, vendors, key people, products/services, channels.

**Concepts** — methodologies, recurring patterns, playbooks. Examples likely to grow:
- `quiet-automation-playbook` (the WildBreeze positioning, what we sell)
- `client-onboarding` (what happens when a new client signs)
- `weekly-report-cadence` (the rhythm of Monday/Tuesday reports per client)
- `mcp-server-recipes` (patterns that work for build-and-bike, weekly-meet, etc.)
- `client-area-architecture` (the gate, the slug, the credentials, the deploy)
- `pricing-and-scope` (what's been quoted, what's been delivered, what's at risk)

**Sources** — each ingest writes one dated page. Examples: a client meeting transcript, a competitor's website, a piece of customer feedback, a published case study, a sales call recording.

## What does NOT go here

- Live site code and design (lives in the project root, governed by `wildbreeze-*` skills)
- Visual/styling rules (those are skill content, not wiki content)
- Personal facts about Jack (in MEMORY.md)
- Session notes (in `../NOTES.md`)
- Site copy or marketing pages (in the repo, not the wiki)

## Operations

- `/wiki-ingest <source>` — file a new source. Updates entities, concepts, sources, index, NOTES log.
- `/wiki-query <question>` — answer from the wiki. Cites pages.
- `/wiki-lint` — monthly health check.

## First ingests worth running

1. **A client meeting transcript** (Read.ai recording) — seeds the relevant client entity and surfaces concept gaps.
2. **A WildBreeze sales conversation** — seeds `concepts/quiet-automation-playbook` and prospects.
3. **The current `~/.claude/wildbreeze/clients.json`** — seeds entity pages for each existing client, one-time bootstrap.
