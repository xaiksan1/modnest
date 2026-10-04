import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'

type Do = { keys: string[]; text: string }
type Mod = {
  id: string; title: string; version: string; tagline: string; summary: string
  does: Do[]; commands: { name: string; text: string }[]; requirements: string[]
  install: { label: string; command: string }[]; installNote: string
  options: [string, string, string][]; privacy: string[]; limits: string[]
}
type Data = { site: { name: string; tagline: string; intro: string; status: string }; mods: Mod[] }

export const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
const e = escapeHtml

const CSP = "default-src 'none'; style-src 'self'; script-src 'self'; img-src data:; base-uri 'none'; form-action 'none'"
const ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23f2b04a'/%3E%3Cpath d='M8 22V10l8 7 8-7v12' fill='none' stroke='%231a1306' stroke-width='3' stroke-linejoin='round'/%3E%3C/svg%3E"

const page = (root: string, title: string, description: string, body: string, data: Data, withScript = false) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="${CSP}">
<title>${e(title)}</title>
<meta name="description" content="${e(description)}">
<link rel="icon" href="${ICON}">
<link rel="stylesheet" href="${root}style.css">
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="${root || './'}">mod<span>nest</span></a>
<span class="status">${e(data.site.status)}</span>
</div></header>
<main><div class="wrap">
${body}
</div></main>
<footer><div class="wrap">
<p>modnest is an independent project, not affiliated with Anthropic. Claude and Claude Code are products of Anthropic.</p>
</div></footer>
${withScript ? `<script src="${root}copy.js"></script>` : ''}
</body>
</html>
`

const home = (data: Data) => page('', `${data.site.name}: ${data.site.tagline}`, data.site.intro, `
<h1>${e(data.site.tagline)}</h1>
<p class="lead">${e(data.site.intro)}</p>
<div class="cards">
${data.mods.map(m => `<a class="card" href="mods/${e(m.id)}/">
<h3>${e(m.title)}</h3>
<p>${e(m.tagline)}</p>
<div class="meta">v${e(m.version)}</div>
</a>`).join('\n')}
</div>`, data)

const kbds = (keys: string[]) => keys.map(k => `<kbd>${e(k)}</kbd>`).join(' + ')

const modPage = (m: Mod, data: Data) => page('../../', `${m.title} · ${data.site.name}`, m.summary, `
<p class="crumb"><a href="../../">← all mods</a></p>
<h1>${e(m.title)}</h1>
<p class="lead">${e(m.summary)}</p>

<h2>What it does</h2>
${m.does.map(d => `<div class="do"><div class="k">${d.keys.length ? kbds(d.keys) : '<span class="label">then</span>'}</div><div>${e(d.text)}</div></div>`).join('\n')}
<p></p>
<table><tbody>
${m.commands.map(c => `<tr><td><code>${e(c.name)}</code></td><td>${e(c.text)}</td></tr>`).join('\n')}
</tbody></table>

<h2>Requirements</h2>
<ul class="plain">${m.requirements.map(r => `<li>${e(r)}</li>`).join('')}</ul>

<h2>Install</h2>
${m.install.map(i => `<div class="label">${e(i.label)}</div>
<div class="cmd"><code>${e(i.command)}</code><button class="copy" type="button" data-copy="${e(i.command)}">Copy</button></div>`).join('\n')}
<p>${e(m.installNote)}</p>

<h2>Options</h2>
<div class="scroll"><table>
<thead><tr><th>Option</th><th>Default</th><th>Meaning</th></tr></thead>
<tbody>
${m.options.map(([n, d, t]) => `<tr><td>${e(n)}</td><td><code>${e(d)}</code></td><td>${e(t)}</td></tr>`).join('\n')}
</tbody></table></div>

<h2>What it sends where</h2>
<ul class="plain">${m.privacy.map(p => `<li>${e(p)}</li>`).join('')}</ul>

<h2>Known limits</h2>
<ul class="plain">${m.limits.map(l => `<li>${e(l)}</li>`).join('')}</ul>
`, data, true)

export function build(out = 'dist') {
  const data: Data = JSON.parse(readFileSync(new URL('./mods.json', import.meta.url), 'utf8'))
  rmSync(out, { recursive: true, force: true })
  mkdirSync(out, { recursive: true })
  writeFileSync(`${out}/index.html`, home(data))
  for (const m of data.mods) {
    mkdirSync(`${out}/mods/${m.id}`, { recursive: true })
    writeFileSync(`${out}/mods/${m.id}/index.html`, modPage(m, data))
  }
  cpSync(new URL('./src/style.css', import.meta.url).pathname, `${out}/style.css`)
  cpSync(new URL('./src/copy.js', import.meta.url).pathname, `${out}/copy.js`)
}

if (import.meta.main) {
  build()
  console.log('built dist/')
}
