import type { EngineInterface, PluginOptions, Register } from 'claude-code'

type Mode = 'dictate' | 'translate'

let options: PluginOptions = {}
let listening: Mode | undefined
let root = ''
let isSpeaking = false
let stopSpeaking = false
let isVoiceTurn = false
let isMuted = false
const stopFile = `/tmp/voice-input-${Math.random().toString(36).slice(2)}.stop` // one per session

const text = (key: string, fallback = '') => String(options[key] ?? fallback)
const python = () => text('python', 'python3')
const keysEnv = (): Record<string, string> => {
  const env: Record<string, string> = {}
  if (text('deepgramApiKey')) env.DEEPGRAM_API_KEY = text('deepgramApiKey')
  if (text('cartesiaApiKey')) env.CARTESIA_API_KEY = text('cartesiaApiKey')
  return env
}

// One tap on the key: start listening, or, if already listening, finish (the text is then sent).
async function pressed($: EngineInterface, mode: Mode) {
  if (isSpeaking) stopSpeaking = true // a tap cuts Claude's voice, then we listen
  try {
    if (listening) await $.fs.write(stopFile, 'stop')
    else await listen($, mode, 'submit', 'hotkey')
  } catch (error) {
    listening = undefined
    $.ui.toast(`🎙 ${error instanceof Error ? error.message : String(error)}`)
  }
}

async function listen($: EngineInterface, mode: Mode, then: 'submit' | 'fill', how: 'hotkey' | 'command') {
  listening = mode
  let heard = ''
  let problem = ''
  try {
    $.ui.status(
      mode === 'translate'
        ? `🌐 translating: speak (${text('language', 'en')}), tap the key to finish`
        : '🎙 listening… tap the key to send',
    )
    const manualStop = how === 'hotkey' ? ['--silence-seconds', '3600', '--wait-seconds', '120', '--max-seconds', '180'] : []
    const recording = $.process.spawn({
      argv: [
        python(), `${root}/bin/mic_stt.py`,
        '--stop-file', stopFile,
        '--language', text('language', 'en'),
        '--device', text('micDevice', 'auto'),
        ...manualStop,
      ],
      env: keysEnv(),
    })
    for await (const piece of recording) {
      if (piece.stream !== 'stdout') continue
      for (const line of piece.text.split('\n')) {
        const [kind, ...rest] = line.split('\t')
        if (kind === 'TEXT') heard = rest.join('\t').trim()
        if (kind === 'ERR') problem = rest.join('\t').trim()
      }
    }
  } catch (error) {
    problem = error instanceof Error ? error.message : String(error)
  } finally {
    listening = undefined
    $.ui.status(undefined)
  }
  if (!heard) {
    $.ui.toast(`🎙 ${problem || 'nothing received'}`)
    return
  }

  if (mode === 'translate') {
    $.ui.status('🌐 translating…')
    const done = await $.model.complete({
      model: 'haiku',
      prompt:
        `Translate the text between the <t> tags into natural ${text('translateTo', 'English')}. ` +
        'Reply with the translation only, no quotes, no commentary.\n<t>' + heard + '</t>',
    })
    $.ui.status(undefined)
    if (!done.isAnswered) {
      $.ui.toast(`🌐 translation failed (${done.reason})`)
      await $.prompt.fill({ text: heard, mode: 'append' }) // keep what was said
      return
    }
    heard = done.text.trim()
  }

  if (then === 'submit') {
    isVoiceTurn = true
    await $.prompt.submit({ text: heard })
  } else await $.prompt.fill({ text: heard, mode: 'append' })
}

// Reads Claude's reply aloud; a long reply is first condensed into a short spoken message.
async function say($: EngineInterface, answer: string) {
  let spoken = answer
  if (spoken.length > 350) {
    const short = await $.model.complete({
      model: 'haiku',
      prompt:
        "Here is a coding assistant's reply to the user. Turn it into a short spoken message in the same language: " +
        '2 to 4 natural sentences, no markdown, no code, no paths or commands to spell out. Give the gist, and say ' +
        'clearly if the user has to do something. Reply with the message only.\n<r>' + answer.slice(0, 6000) + '</r>',
    })
    if (short.isAnswered) spoken = short.text
  }
  isSpeaking = true
  stopSpeaking = false
  try {
    const voice = $.process.spawn({
      argv: [
        python(), `${root}/bin/speak.py`,
        '--language', text('language', 'en'),
        '--voice', text('voiceId'),
        '--device', text('speakerDevice', 'default'),
      ],
      env: keysEnv(),
      input: spoken,
    })
    for await (const piece of voice) {
      if (stopSpeaking) break // leaving the loop stops playback
      if (piece.stream === 'stdout' && piece.text.startsWith('ERR')) $.ui.toast(`🔊 ${piece.text.split('\t')[1] ?? ''}`)
    }
  } finally {
    isSpeaking = false
    stopSpeaking = false
  }
}

export const register: Register = (on, config) => {
  options = config

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (isVoiceTurn && !e.agentId) {
      isVoiceTurn = false
      if (options.speakReplies !== false && !isMuted && e.reason === 'answer' && e.answer.trim()) {
        void say($, e.answer).catch(error => $.ui.toast(`🔊 ${error instanceof Error ? error.message : String(error)}`))
      }
    }
    return done
  })

  on('session.start', async ($, e, next) => {
    root = $.plugin.root
    await $.command.register({
      name: 'voice',
      description: 'Dictate to the prompt: /voice (fill), /voice go (send), /voice stop, /voice mute. Hotkey: Right Ctrl.',
    })

    // The hotkey: tap = dictate / send, with the chord key held = translate.
    void (async () => {
      try {
        const keys = $.process.spawn({
          argv: [python(), `${root}/bin/hotkey.py`, String(options.toggleKeycode ?? 105), String(options.chordKeycode ?? 65)],
        })
        for await (const piece of keys) {
          if (piece.stream !== 'stdout') continue
          for (const line of piece.text.split('\n')) {
            const [word, ...rest] = line.trim().split('\t')
            if (word === 'TOGGLE') void pressed($, 'dictate')
            else if (word === 'TRANSLATE') void pressed($, 'translate')
            else if (word === 'ERR') $.ui.toast(`🎙 hotkey: ${rest.join(' ')}`)
          }
        }
      } catch {
        $.ui.toast('🎙 the hotkey is unavailable')
      }
    })()

    return next(e)
  })

  on('command.run', { command: 'voice' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    if (arg === 'stop') {
      if (!listening) return { text: 'Not listening.' }
      await $.fs.write(stopFile, 'stop')
      return { text: 'Finishing…' }
    }
    if (arg === 'mute') {
      isMuted = !isMuted
      if (isMuted) stopSpeaking = true
      return { text: isMuted ? '🔇 Claude will no longer speak aloud.' : '🔊 Claude will speak again.' }
    }
    if (arg !== '' && arg !== 'go') return { text: 'Usage: /voice, /voice go, /voice stop or /voice mute.' }
    if (listening) return { text: 'Already listening: speak, or /voice stop.' }
    void listen($, 'dictate', arg === 'go' ? 'submit' : 'fill', 'command').catch(error => {
      listening = undefined
      $.ui.toast(`🎙 ${error instanceof Error ? error.message : String(error)}`)
    })
    return { text: '🎙 Listening…' }
  })
}
