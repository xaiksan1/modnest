import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

import type { Phase } from '../types'

type Mode = 'dictate' | 'translate'

const phase = atom({ plugin: 'igor', key: 'phase' } as const, 'idle' as Phase)
const frame = atom({ plugin: 'igor', key: 'frame' } as const, 0)

let options: PluginOptions = {}
let listening: Mode | undefined
let root = ''
let isSpeaking = false
let stopSpeaking = false
let isVoiceTurn = false
let isMuted = false
let currentPhase: Phase = 'idle'
let ticker: { cancel: () => void } | undefined
const stopFile = `/tmp/igor-${Math.random().toString(36).slice(2)}.stop` // one per session

const text = (key: string, fallback = '') => String(options[key] ?? fallback)
const python = () => text('python', 'python3')
const envFileArgs = () => (text('envFile') ? ['--env', text('envFile')] : [])
const keysEnv = (): Record<string, string> => {
  const env: Record<string, string> = {}
  if (text('deepgramApiKey')) env.DEEPGRAM_API_KEY = text('deepgramApiKey')
  if (text('cartesiaApiKey')) env.CARTESIA_API_KEY = text('cartesiaApiKey')
  return env
}
const message = (error: unknown) => (error instanceof Error ? error.message : String(error))
const rest = (): Phase => (isMuted ? 'muted' : 'idle')

async function setPhase($: EngineInterface, next: Phase) {
  currentPhase = next
  await update($, phase, () => next)
}

// One tap on the key: start listening, or, if already listening, finish (the text is then sent).
async function pressed($: EngineInterface, mode: Mode) {
  if (isSpeaking) stopSpeaking = true // a tap cuts IGOR's voice, then we listen
  try {
    if (listening) await $.fs.write(stopFile, 'stop')
    else await listen($, mode, 'submit', 'hotkey')
  } catch (error) {
    listening = undefined
    await setPhase($, rest())
    $.ui.toast(`IGOR: ${message(error)}`)
  }
}

async function listen($: EngineInterface, mode: Mode, then: 'submit' | 'fill', how: 'hotkey' | 'command') {
  listening = mode
  await setPhase($, mode === 'translate' ? 'translating' : 'listening')
  let heard = ''
  let problem = ''
  try {
    const manualStop = how === 'hotkey' ? ['--silence-seconds', '3600', '--wait-seconds', '120', '--max-seconds', '180'] : []
    const recording = $.process.spawn({
      argv: [
        python(), `${root}/bin/mic_stt.py`,
        '--stop-file', stopFile,
        ...envFileArgs(),
        '--language', text('language', 'en'),
        '--keyterms', text('keyterms', 'Igor'),
        '--device', text('micDevice', 'auto'),
        ...manualStop,
      ],
      env: keysEnv(),
    })
    for await (const piece of recording) {
      if (piece.stream !== 'stdout') continue
      for (const line of piece.text.split('\n')) {
        const [kind, ...parts] = line.split('\t')
        if (kind === 'TEXT') heard = parts.join('\t').trim()
        if (kind === 'ERR') problem = parts.join('\t').trim()
      }
    }
  } catch (error) {
    problem = message(error)
  } finally {
    listening = undefined
  }
  if (!heard) {
    await setPhase($, rest())
    $.ui.toast(`IGOR: ${problem || 'nothing received'}`)
    return
  }

  if (mode === 'translate') {
    await setPhase($, 'thinking')
    const done = await $.model.complete({
      model: 'haiku',
      prompt:
        `Translate the text between the <t> tags into natural ${text('translateTo', 'English')}. ` +
        'Reply with the translation only, no quotes, no commentary.\n<t>' + heard + '</t>',
    })
    if (!done.isAnswered) {
      await setPhase($, rest())
      $.ui.toast(`IGOR: translation failed (${done.reason})`)
      await $.prompt.fill({ text: heard, mode: 'append' }) // keep what was said
      return
    }
    heard = done.text.trim()
  }

  if (then === 'submit') {
    isVoiceTurn = true
    await setPhase($, 'thinking')
    await $.prompt.submit({ text: heard })
  } else {
    await setPhase($, rest())
    await $.prompt.fill({ text: heard, mode: 'append' })
  }
}

const LANGUAGES: Record<string, string> = { en: 'English', fr: 'French', de: 'German', es: 'Spanish', it: 'Italian', pt: 'Portuguese', nl: 'Dutch' }
// The language a machine voice speaks, from its eSpeak name: "en-us+klatt4" -> English.
const machineLanguage = () => {
  const code = text('machineVoice', 'en-us+klatt4').split('+')[0]!.split('-')[0]!
  return LANGUAGES[code] ?? code
}

// IGOR reads Claude's reply aloud. A machine voice speaks one language, so the reply is first turned into a short
// spoken message in that language; a human-like voice only condenses a long reply.
async function say($: EngineInterface, answer: string) {
  const isMachine = text('voiceEngine', 'machine') === 'machine'
  let spoken = answer
  const isPlainAscii = !/[^\x00-\x7f]/.test(answer)
  if (isMachine ? !(isPlainAscii && answer.length <= 350) : answer.length > 350) {
    const language = isMachine ? `in ${machineLanguage()}` : 'in the same language'
    const short = await $.model.complete({
      model: 'haiku',
      prompt:
        `Here is a coding assistant's reply to the user. Turn it into a short spoken message ${language}: ` +
        '2 to 4 plain sentences, no markdown, no code, no paths or commands to spell out, no abbreviations or symbols ' +
        'a speech synthesizer would stumble on. Give the gist, and say clearly if the user has to do something. ' +
        'Reply with the message only.\n<r>' + answer.slice(0, 6000) + '</r>',
    })
    if (short.isAnswered) spoken = short.text
    else if (isMachine) {
      $.ui.toast('IGOR: could not prepare the spoken message')
      return
    }
  }
  isSpeaking = true
  stopSpeaking = false
  await setPhase($, 'speaking')
  try {
    const voice = $.process.spawn({
      argv: [
        python(), `${root}/bin/speak.py`,
        ...envFileArgs(),
        '--engine', text('voiceEngine', 'machine'),
        '--machine-voice', text('machineVoice', 'en-us+klatt4'),
        '--language', text('language', 'en'),
        '--voice', text('voiceId'),
        '--style', text('voiceStyle', 'robot'),
        '--speed', String(Number(options.voiceSpeed ?? 0.9)),
        '--device', text('speakerDevice', 'default'),
      ],
      env: keysEnv(),
      input: spoken,
    })
    for await (const piece of voice) {
      if (stopSpeaking) break // leaving the loop stops playback
      if (piece.stream === 'stdout' && piece.text.startsWith('ERR')) $.ui.toast(`IGOR: ${piece.text.split('\t')[1] ?? ''}`)
    }
  } finally {
    isSpeaking = false
    stopSpeaking = false
    if (!listening) await setPhase($, rest())
  }
}

const LABEL: Record<Phase, string> = {
  idle: 'tap Right Ctrl to talk',
  listening: 'listening, tap Right Ctrl to send',
  translating: 'translating, tap Right Ctrl to send',
  thinking: 'thinking',
  speaking: 'speaking, tap Right Ctrl to interrupt',
  muted: 'muted (/igor mute)',
}
const COLOR: Record<Phase, string> = { idle: 'gray', listening: 'green', translating: 'yellow', thinking: 'magenta', speaking: 'cyan', muted: 'gray' }
const BARS = '▁▂▃▄▅▆▇█'

// A little level meter that moves while IGOR listens or speaks.
const meter = (tick: number, width = 12) =>
  Array.from({ length: width }, (_, i) => BARS[Math.min(7, Math.floor(Math.abs(Math.sin(tick * 0.9 + i * 1.7)) * 8))]).join('')

export const register: Register = (on, config) => {
  options = config

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (isVoiceTurn && !e.agentId) {
      isVoiceTurn = false
      const willSpeak = options.speakReplies !== false && !isMuted && e.reason === 'answer' && e.answer.trim() !== ''
      if (willSpeak) void say($, e.answer).catch(error => { $.ui.toast(`IGOR: ${message(error)}`); void setPhase($, rest()) })
      else await setPhase($, rest())
    }
    return done
  })

  on('session.start', async ($, e, next) => {
    root = $.plugin.root
    await $.command.register({
      name: 'igor',
      description: 'IGOR voice: /igor (dictate into the prompt), /igor go (dictate and send), /igor stop, /igor mute. Hotkey: Right Ctrl.',
    })

    ticker?.cancel()
    ticker = $.clock.every(300, () => {
      if (currentPhase !== 'idle' && currentPhase !== 'muted') void update($, frame, n => (n ?? 0) + 1)
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
            const [word, ...parts] = line.trim().split('\t')
            if (word === 'TOGGLE') void pressed($, 'dictate')
            else if (word === 'TRANSLATE') void pressed($, 'translate')
            else if (word === 'ERR') $.ui.toast(`IGOR: hotkey ${parts.join(' ')}`)
          }
        }
      } catch {
        $.ui.toast('IGOR: the hotkey is unavailable')
      }
    })()

    return next(e)
  })

  on('command.run', { command: 'igor' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    if (arg === 'stop') {
      if (!listening) return { text: 'IGOR is not listening.' }
      await $.fs.write(stopFile, 'stop')
      return { text: 'IGOR: finishing…' }
    }
    if (arg === 'mute') {
      isMuted = !isMuted
      if (isMuted) stopSpeaking = true
      if (currentPhase === 'idle' || currentPhase === 'muted') await setPhase($, rest())
      return { text: isMuted ? 'IGOR will stay quiet.' : 'IGOR will speak again.' }
    }
    if (arg !== '' && arg !== 'go') return { text: 'Usage: /igor, /igor go, /igor stop or /igor mute.' }
    if (listening) return { text: 'IGOR is already listening: speak, or /igor stop.' }
    void listen($, 'dictate', arg === 'go' ? 'submit' : 'fill', 'command').catch(async error => {
      listening = undefined
      await setPhase($, rest())
      $.ui.toast(`IGOR: ${message(error)}`)
    })
    return { text: 'IGOR is listening…' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (options.showBand === false || e.props.hasSurvey) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const now = (await read($, phase)) ?? 'idle'
    const tick = (await read($, frame)) ?? 0
    const color = COLOR[now]
    const live = now === 'listening' || now === 'translating' || now === 'speaking'
    const dots = '.'.repeat((tick % 3) + 1)

    return (
      <Box>
        <Text bold inverse color={color}> IGOR </Text>
        <Text color={color}> {live ? meter(tick) : now === 'thinking' ? dots.padEnd(3) : '·'} </Text>
        <Text dimColor>{LABEL[now]}</Text>
      </Box>
    )
  })
}
