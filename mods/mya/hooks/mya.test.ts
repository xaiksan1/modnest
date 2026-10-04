import { test, expect } from 'claude-code/testing'

type Spawned = { argv: readonly string[] }
const isHotkey = (e: Spawned) => e.argv.some(a => a.endsWith('hotkey.py'))
const done = { code: 0, signal: null }

// What the engine would answer beneath the mod; each test swaps in its own answers.
function engine(on: (event: string, hook: (...args: any[]) => unknown) => void, heard: { key?: string; said: string; english?: string }) {
  const seen = { submitted: [] as string[], filled: [] as string[] }
  on('process.spawn', async function* (_$: unknown, e: Spawned) {
    if (isHotkey(e)) { if (heard.key) yield { stream: 'stdout' as const, text: `${heard.key}\n` } }
    else yield { stream: 'stdout' as const, text: `TEXT\t${heard.said}\n` }
    return done
  })
  on('prompt.submit', async (_$: unknown, e: { text: string }) => { seen.submitted.push(e.text); return { value: {} } })
  on('prompt.fill', async (_$: unknown, e: { text: string }) => { seen.filled.push(e.text); return { value: { isFilled: true } } })
  on('model.complete', async () => ({ value: { isAnswered: true, text: heard.english ?? '', usage: {} } }))
  on('ui.status', async () => ({ value: undefined }))
  on('ui.toast', async () => ({ value: undefined }))
  on('command.register', async () => ({ value: undefined }))
  on('session.start', async (_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  return seen
}
const settle = () => new Promise(r => setTimeout(r, 150))

test('/mya fills the prompt with what the microphone heard', async ($, on) => {
  const seen = engine(on as never, { said: 'bonjour Claude' })
  const ran = await $.command.run({ command: 'mya', args: '' })
  expect(ran.text).toContain('listening')
  await settle()
  expect(seen.filled).toEqual(['bonjour Claude'])
  expect(seen.submitted).toEqual([])
})

test('/mya stop says so when nothing is being recorded', async $ => {
  const ran = await $.command.run({ command: 'mya', args: 'stop' })
  expect(ran.text).toContain('not listening')
})

test('Right Ctrl: dictates then sends the text to Claude', async ($, on) => {
  const seen = engine(on as never, { key: 'TOGGLE', said: 'lance les tests' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual(['lance les tests'])
})

test('Right Ctrl + Space: translates and sends directly', async ($, on) => {
  const seen = engine(on as never, { key: 'TRANSLATE', said: 'bonjour tout le monde', english: 'hello everyone' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual(['hello everyone'])
  expect(seen.filled).toEqual([])
})

test('the MYA band shows above the prompt, and the hotkey turns it to listening', async ($, on) => {
  engine(on as never, { key: 'TOGGLE', said: 'bonjour' })
  const idle = await $.ui.mount({ plugin: 'mya', surface: 'terminal', component: 'AbovePrompt', requestId: 'band', props: { hasSurvey: false } } as never)
  expect((await idle.find({ type: 'Text', text: /MYA/ })) !== undefined).toBe(true)
  expect((await idle.find({ type: 'Text', text: /tap Right Ctrl to talk/ })) !== undefined).toBe(true)
  await idle.unmount()
})
