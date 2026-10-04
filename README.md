# modnest

Small mods for [Claude Code](https://code.claude.com), and the static site that lists them.

| Mod | What it does |
|---|---|
| [voice-input](mods/voice-input/) | Tap-to-talk dictation, one-key translation and spoken replies (Linux/X11) |

Load a mod with `claude --plugin-dir mods/<name>`. Each mod folder has its own README saying what it needs and what it sends where.

## The site

No dependencies.

```bash
bun run build   # writes dist/
bun run serve   # builds, then serves on http://127.0.0.1:3098
bun test ./tests                        # the site; mods are tested with: claude plugin test mods/<name>
```

Add a mod by adding a folder under `mods/` and an entry in `mods.json`; the home page and the mod's page are generated. Content is escaped, pages carry a strict CSP (no inline script, no external resource).

modnest is an independent project, not affiliated with Anthropic. Claude and Claude Code are products of Anthropic.

## License

MIT, see [LICENSE](LICENSE).
