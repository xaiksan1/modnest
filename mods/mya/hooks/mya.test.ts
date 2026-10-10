import { test, expect, mock } from 'claude-code/testing'

type Spawned = { argv: readonly string[] }
const isHotkey = (e: Spawned) => e.argv.some(a => a.endsWith('hotkey.py'))
const done = { value: { code: 0, signal: null } }
const USAGE = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }

// What the engine would answer beneath the mod; each test swaps in its own answers.
function engine(on: (event: string, hook: (...args: any[]) => unknown) => void, heard: { key?: string; said: string; english?: string }) {
  const seen = { submitted: [] as string[], filled: [] as string[], toasts: [] as string[] }
  mock.clock(on as never)                                       // the engine now gives timers (the band's ticker) only to a test that asks for them
  on('process.spawn', async function* (_$: unknown, e: Spawned) {
    if (isHotkey(e)) { if (heard.key) yield { stream: 'stdout' as const, text: `${heard.key}\n` } }
    else yield { stream: 'stdout' as const, text: `TEXT\t${heard.said}\n` }
    return done
  })
  on('prompt.submit', async (_$: unknown, e: { text: string }) => { seen.submitted.push(e.text); return { text: e.text } })
  on('prompt.fill', async (_$: unknown, e: { text: string }) => { seen.filled.push(e.text); return { isFilled: true } })
  on('model.complete', async () => ({ value: { isAnswered: true, text: heard.english ?? '', usage: USAGE } }))
  on('ui.status', async () => ({ value: undefined }))
  on('ui.toast', async (_$: unknown, e: { text?: string }) => { seen.toasts.push(String(e.text ?? '')); return { value: undefined } })
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
  mock.clock(on as never)
  on('process.spawn' as never, async function* (_$: unknown, e: { argv: readonly string[]; input?: string }) {
    if (isHotkey(e)) yield { stream: 'stdout' as const, text: 'TOGGLE\n' }
    else if (e.argv.some(a => a.endsWith('speak.py'))) spoke.spawned.push({ argv: e.argv, input: e.input })
    else yield { stream: 'stdout' as const, text: 'TEXT\tbonjour\n' }
    return done
  })
  on('prompt.submit' as never, async (_$: unknown, e: { text: string }) => ({ text: e.text }))
  on('prompt.fill' as never, async () => ({ isFilled: true }))
  on('model.complete' as never, async (_$: unknown, e: { prompt: string }) => { spoke.prompts.push(e.prompt); return { value: { isAnswered: true, text: 'Voici le résumé parlé.', usage: USAGE } } })
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
  mock.clock(on as never)
  on('process.spawn' as never, async function* (_$: unknown, e: { argv: readonly string[]; input?: string }) {
    if (isHotkey(e)) yield { stream: 'stdout' as const, text: 'TOGGLE\n' }
    else if (e.argv.some(a => a.endsWith('speak.py'))) spoke.spawned.push({ input: e.input })
    else yield { stream: 'stdout' as const, text: 'TEXT\tbonjour\n' }
    return done
  })
  on('prompt.submit' as never, async (_$: unknown, e: { text: string }) => ({ text: e.text }))
  on('prompt.fill' as never, async () => ({ isFilled: true }))
  on('model.complete' as never, async (_$: unknown, e: { prompt: string }) => { spoke.prompts.push(e.prompt); return { value: { isAnswered: true, text: 'x', usage: USAGE } } })
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
  const clock = mock.clock(on as never)                          // the retry waits are virtual: the test moves the clock instead of sleeping
  on('process.spawn' as never, async function* (_$: unknown, e: Spawned) {
    if (isHotkey(e)) {
      seen.starts += 1
      if (seen.starts === 3) yield { stream: 'stdout' as const, text: 'TOGGLE\n' } // the third listener works (the others die at once)
      else yield { stream: 'stdout' as const, text: 'ERR\txinput stopped\n' }       // the first two die at once
    } else yield { stream: 'stdout' as const, text: 'TEXT\tça remarche\n' }
    return done
  })
  on('prompt.submit' as never, async (_$: unknown, e: { text: string }) => { seen.submitted.push(e.text); return { text: e.text } })
  on('prompt.fill' as never, async () => ({ isFilled: true }))
  on('model.complete' as never, async () => ({ value: { isAnswered: true, text: '', usage: USAGE } }))
  on('ui.status' as never, async () => ({ value: undefined }))
  on('ui.toast' as never, async () => ({ value: undefined }))
  on('command.register' as never, async () => ({ value: undefined }))
  on('session.start' as never, async (_$: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/tmp' } as never)
  await clock.advance(5_000)
  expect(seen.starts).toBeGreaterThanOrEqual(3)
  expect(seen.submitted).toEqual(['ça remarche'])
})

// -- Wayland : the helper announces `MODE socket`, and the keys are GNOME shortcuts (Ctrl+Alt+M…), not Right Ctrl ------------
const mountBand = ($: any) => $.ui.mount({ plugin: 'mya', surface: 'terminal', component: 'AbovePrompt', requestId: 'band', props: { hasSurvey: false } } as never)

test('under Wayland the band names the real shortcut, not Right Ctrl', async ($, on) => {
  engine(on as never, { key: 'MODE\tsocket', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  const band = await mountBand($)
  expect((await band.find({ type: 'Text', text: /tap Ctrl\+Alt\+M to talk/ })) !== undefined).toBe(true)
  expect((await band.find({ type: 'Text', text: /Right Ctrl/ })) === undefined).toBe(true)
  await band.unmount()
})

test('under Wayland /mya off names the on/off shortcut', async ($, on) => {
  engine(on as never, { key: 'MODE\tsocket', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  const off = await $.command.run({ command: 'mya', args: 'off' })
  expect(off.text).toContain('Ctrl+Alt+K')
  expect(off.text).not.toContain('Right Ctrl')
})

test('under Wayland, with the hotkey off, the band says which shortcut turns it back on', { options: { hotkeyOnStart: false } }, async ($, on) => {
  engine(on as never, { key: 'MODE\tsocket', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  const band = await mountBand($)
  expect((await band.find({ type: 'Text', text: /hotkey off, Ctrl\+Alt\+K or \/mya on/ })) !== undefined).toBe(true)
  await band.unmount()
})

test('without a MODE line (X11) the messages still say Right Ctrl', async ($, on) => {
  engine(on as never, { said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  const off = await $.command.run({ command: 'mya', args: 'off' })
  expect(off.text).toContain('Right Ctrl + Right Shift')
})

test('an unknown MODE falls back to the X11 names instead of showing nonsense', async ($, on) => {
  engine(on as never, { key: 'MODE\tbanana', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  const off = await $.command.run({ command: 'mya', args: 'off' })
  expect(off.text).toContain('Right Ctrl + Right Shift')
})

test('a Wayland shortcut word still dictates and sends (TOGGLE after MODE)', async ($, on) => {
  const seen = engine(on as never, { key: 'MODE\tsocket\nTOGGLE', said: 'bonjour de Wayland' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual(['bonjour de Wayland'])
})

test('a Wayland TRANSLATE word translates and sends', async ($, on) => {
  const seen = engine(on as never, { key: 'MODE\tsocket\nTRANSLATE', said: 'bonjour tout le monde', english: 'hello everyone' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual(['hello everyone'])
})

test('a Wayland LOCK word switches the hotkey off and TOGGLE then does nothing', async ($, on) => {
  const seen = engine(on as never, { key: 'MODE\tsocket\nLOCK\nTOGGLE', said: 'should not be heard' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.submitted).toEqual([])
})

test('the toast after the lock word names the shortcut of the mode: GNOME under Wayland, Right Ctrl on X11', async ($, on) => {
  const seen = engine(on as never, { key: 'MODE\tsocket\nLOCK', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.toasts.some(t => t.includes('hotkey off') && t.includes('Ctrl+Alt+K') && !t.includes('Right Ctrl'))).toBe(true)
})

test('on X11 the lock toast still says Right Ctrl + Right Shift', async ($, on) => {
  const seen = engine(on as never, { key: 'LOCK', said: 'x' })
  await $.session.start({ cwd: '/tmp' } as never)
  await settle()
  expect(seen.toasts.some(t => t.includes('hotkey off') && t.includes('Right Ctrl + Right Shift'))).toBe(true)
})
