import { build } from './build'
import { existsSync, statSync } from 'node:fs'

build()
const root = `${import.meta.dir}/dist`
const types: Record<string, string> = { html: 'text/html; charset=utf-8', css: 'text/css', js: 'text/javascript' }

Bun.serve({
  hostname: '127.0.0.1',
  port: 3098,
  fetch(req) {
    let path = decodeURIComponent(new URL(req.url).pathname)
    if (path.includes('..')) return new Response('Not found', { status: 404 })
    let file = `${root}${path}`
    if (existsSync(file) && statSync(file).isDirectory()) file = `${file.replace(/\/$/, '')}/index.html`
    if (!existsSync(file)) return new Response('Not found', { status: 404 })
    const ext = file.split('.').pop() ?? ''
    return new Response(Bun.file(file), { headers: { 'content-type': types[ext] ?? 'application/octet-stream', 'x-content-type-options': 'nosniff' } })
  },
})
console.log('modnest on http://127.0.0.1:3098')
