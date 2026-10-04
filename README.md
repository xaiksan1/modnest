# modnest

Static site for small Claude Code mods. No dependencies.

```bash
bun run build   # writes dist/
bun run serve   # builds, then serves on http://127.0.0.1:3098
bun test
```

Add a mod by adding an entry to `mods.json`; the home page and its page are generated. Content is escaped, pages carry a strict CSP (no inline script, no external resource).
