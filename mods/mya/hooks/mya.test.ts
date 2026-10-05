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

test('with the hotkey off, tapping Right Ctrl does nothing and the band says so', { options: { hotkeyOnStart: false } }, async ($, on) => {
  const seen = engine(on as never, { key: 'TOGGLE', said: 'should not be heard' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual([])
  const band = await $.ui.mount({ plugin: 'mya', surface: 'terminal', component: 'AbovePrompt', requestId: 'band', props: { hasSurvey: false } } as never)
  expect((await band.find({ type: 'Text', text: /hotkey off/ })) !== undefined).toBe(true)
  await band.unmount()
})

test('/mya on and /mya off switch the hotkey', async ($, on) => {
  engine(on as never, { said: 'x' })
  const off = await $.command.run({ command: 'mya', args: 'off' })
  expect(off.text).toContain('off')
  const again = await $.command.run({ command: 'mya', args: 'on' })
  expect(again.text).toContain('is on')
})

test('a Piper voice speaks ONE language: even a short English reply is turned into a message in the voice\'s language (French)', { options: { voiceEngine: 'piper', piperModel: '/m/fr_FR-siwis-medium.onnx' } }, async ($, on) => {
  const spoke = { prompts: [] as string[], spawned: [] as { argv: readonly string[]; input?: string }[] }
  on('process.spawn' as never, async function* (_$: unknown, e: { argv: readonly string[]; input?: string }) {
    if (isHotkey(e)) yield { stream: 'stdout' as const, text: 'TOGGLE\n' }
    else if (e.argv.some(a => a.endsWith('speak.py'))) spoke.spawned.push({ argv: e.argv, input: e.input })
    else yield { stream: 'stdout' as const, text: 'TEXT\tbonjour\n' }
    return done
  })
  on('prompt.submit' as never, async () => ({ value: {} }))
  on('prompt.fill' as never, async () => ({ value: { isFilled: true } }))
  on('model.complete' as never, async (_$: unknown, e: { prompt: string }) => { spoke.prompts.push(e.prompt); return { value: { isAnswered: true, text: 'Voici le résumé parlé.', usage: {} } } })
  on('ui.status' as never, async () => ({ value: undefined }))
  on('ui.toast' as never, async () => ({ value: undefined }))
  on('command.register' as never, async () => ({ value: undefined }))
  on('session.start' as never, async (_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('turn.complete' as never, async (_$: unknown, e: { answer: string }) => ({ text: e.answer }))
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()                                                      // the voice turn is submitted: MYA now expects the answer
  await $.turn.complete({ answer: 'Done. Tests pass.', durationMs: 5, isAborted: false, turnId: 't1', reason: 'answer' } as never)
  await settle()
  expect(spoke.prompts.length).toBe(1)
  expect(spoke.prompts[0]).toContain('in French')
  expect(spoke.prompts[0]).toContain('MUST be written entirely in French')
  expect(spoke.spawned[0]?.input).toBe('Voici le résumé parlé.')
  expect(spoke.spawned[0]?.argv).toContain('--piper-model')
})

test('a Cartesia voice still reads a short reply as it is (no model call)', async ($, on) => {
  const spoke = { prompts: [] as string[], spawned: [] as { input?: string }[] }
  on('process.spawn' as never, async function* (_$: unknown, e: { argv: readonly string[]; input?: string }) {
    if (isHotkey(e)) yield { stream: 'stdout' as const, text: 'TOGGLE\n' }
    else if (e.argv.some(a => a.endsWith('speak.py'))) spoke.spawned.push({ input: e.input })
    else yield { stream: 'stdout' as const, text: 'TEXT\tbonjour\n' }
    return done
  })
  on('prompt.submit' as never, async () => ({ value: {} }))
  on('prompt.fill' as never, async () => ({ value: { isFilled: true } }))
  on('model.complete' as never, async (_$: unknown, e: { prompt: string }) => { spoke.prompts.push(e.prompt); return { value: { isAnswered: true, text: 'x', usage: {} } } })
  on('ui.status' as never, async () => ({ value: undefined }))
  on('ui.toast' as never, async () => ({ value: undefined }))
  on('command.register' as never, async () => ({ value: undefined }))
  on('session.start' as never, async (_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('turn.complete' as never, async (_$: unknown, e: { answer: string }) => ({ text: e.answer }))
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  await $.turn.complete({ answer: 'Tout est bon.', durationMs: 5, isAborted: false, turnId: 't2', reason: 'answer' } as never)
  await settle()
  expect(spoke.prompts.length).toBe(0)
  expect(spoke.spawned[0]?.input).toBe('Tout est bon.')
})

test('if the hotkey listener stops (xinput died), MYA starts it again by itself', { options: { hotkeyRetryMs: 10 } }, async ($, on) => {
  const seen = { starts: 0, submitted: [] as string[] }
  on('process.spawn' as never, async function* (_$: unknown, e: Spawned) {
    if (isHotkey(e)) {
      seen.starts += 1
      if (seen.starts === 3) yield { stream: 'stdout' as const, text: 'TOGGLE\n' } // the third listener works (the others die at once)
      else yield { stream: 'stdout' as const, text: 'ERR\txinput stopped\n' }       // the first two die at once
    } else yield { stream: 'stdout' as const, text: 'TEXT\tça remarche\n' }
    return done
  })
  on('clock.sleep' as never, async (_$: unknown, e: { ms?: number } | number) => { await new Promise(r => setTimeout(r, 5)); return { value: undefined } })
  on('prompt.submit' as never, async (_$: unknown, e: { text: string }) => { seen.submitted.push(e.text); return { value: {} } })
  on('prompt.fill' as never, async () => ({ value: { isFilled: true } }))
  on('model.complete' as never, async () => ({ value: { isAnswered: true, text: '', usage: {} } }))
  on('ui.status' as never, async () => ({ value: undefined }))
  on('ui.toast' as never, async () => ({ value: undefined }))
  on('command.register' as never, async () => ({ value: undefined }))
  on('session.start' as never, async (_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/tmp' } as never)
  await new Promise(r => setTimeout(r, 400))
  expect(seen.starts).toBeGreaterThanOrEqual(3)
  expect(seen.submitted).toEqual(['ça remarche'])
})
