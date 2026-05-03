# WildBreeze

Quiet automation infrastructure for operations run by humans.

- Custom MCP servers
- Scheduled agents
- Weekly reports

## Live site

- Custom domain: https://www.wildbreeze.io
- GitHub Pages fallback: https://jackmichaelnapier.github.io/project-wildbreeze/

## Repo contents

- `index.html` — the entire site, single self-contained file (no build step,
  no framework, only Google Fonts as an external dependency).
- `CNAME` — custom domain binding for GitHub Pages.

## Editing

Edit `index.html` directly. The design system is documented in the
`wildbreeze-design` Claude Code skill (file: `~/.claude/skills/wildbreeze-design/SKILL.md`).

## DNS setup

For `www.wildbreeze.io` to resolve to this Pages site, the DNS record at
your registrar should be:

    www.wildbreeze.io   CNAME   jackmichaelnapier.github.io

For the apex `wildbreeze.io` (if you want it to redirect to www), set
A records pointing to GitHub Pages IPs:

    185.199.108.153
    185.199.109.153
    185.199.110.153
    185.199.111.153

GitHub will issue an HTTPS certificate automatically once DNS resolves and
the CNAME file is committed.
