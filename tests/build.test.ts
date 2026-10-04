import { beforeAll, expect, test } from 'bun:test'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { build, escapeHtml } from '../build'

const out = '/tmp/modnest-test-dist'
const read = (p: string) => readFileSync(`${out}/${p}`, 'utf8')

beforeAll(() => {
  rmSync(out, { recursive: true, force: true })
  build(out)
})

test('escapeHtml neutralises markup', () => {
  expect(escapeHtml(`<img src=x onerror="a()">&'`)).toBe('&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;')
})

test('the site has a home page, a page per mod, and its assets', () => {
  for (const f of ['index.html', 'mods/igor/index.html', 'style.css', 'copy.js']) expect(existsSync(`${out}/${f}`)).toBe(true)
})

test('the home page lists every mod and links to its page', () => {
  const home = read('index.html')
  expect(home).toContain('modnest')
  expect(home).toContain('href="mods/igor/"')
  expect(home).toContain('IGOR')
})

test('a mod page carries install, options, privacy and limits', () => {
  const page = read('mods/igor/index.html')
  for (const word of ['Install', 'Options', 'What it sends where', 'Known limits', 'Requirements', 'claude --plugin-dir']) expect(page).toContain(word)
  expect(page).toContain('<kbd>Right Ctrl</kbd>')
})

test('every page says it is unofficial', () => {
  for (const f of ['index.html', 'mods/igor/index.html']) expect(read(f)).toContain('not affiliated with Anthropic')
})

test('no inline script, no external resource, a strict CSP', () => {
  for (const f of ['index.html', 'mods/igor/index.html']) {
    const html = read(f)
    expect(html).toContain("Content-Security-Policy")
    expect(html).toContain("default-src 'none'")
    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)/i)
    expect(html).not.toMatch(/src="https?:\/\//i)                                  // nothing loaded from elsewhere
    for (const [, href] of html.matchAll(/href="(https?:\/\/[^"]*)"/g)) expect(href).toBe('https://github.com/xaiksan1/modnest')  // the only outside link
  }
})

test('relative links resolve to files that exist', () => {
  for (const f of ['index.html', 'mods/igor/index.html']) {
    const base = f.includes('/') ? f.slice(0, f.lastIndexOf('/') + 1) : ''
    for (const [, href] of read(f).matchAll(/(?:href|src)="([^"#:]+)"/g)) {
      const target = `${out}/${base}${href}`.replace(/\/$/, '/index.html')
      expect(existsSync(target)).toBe(true)
    }
  }
})
