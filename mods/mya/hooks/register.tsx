import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

import type { Phase } from '../types'

type Mode = 'dictate' | 'translate'

const phase = atom({ plugin: 'mya', key: 'phase' } as const, 'idle' as Phase)
const frame = atom({ plugin: 'mya', key: 'frame' } as const, 0)

let options: PluginOptions = {}
let listening: Mode | undefined
let root = ''
let isSpeaking = false
let stopSpeaking = false
let isVoiceTurn = false
let isMuted = false
let isKeysOn = true // the Right Ctrl hotkey: on, or off while you copy-paste elsewhere
let currentPhase: Phase = 'idle'
let ticker: { cancel: () => void } | undefined
const stopFile = `/tmp/mya-${Math.random().toString(36).slice(2)}.stop` // one per session

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
const rest = (): Phase => (!isKeysOn ? 'off' : isMuted ? 'muted' : 'idle')

// Claude has finished: the phone rings until you answer.
async function waitForYou($: EngineInterface, isAnswer: boolean) {
  if (listening || isSpeaking) return
  await setPhase($, isAnswer && !isMuted ? 'waiting' : rest())
  if (isAnswer) ring($)
}

async function setPhase($: EngineInterface, next: Phase) {
  currentPhase = next
  await update($, phase, () => next)
}

// Switch the hotkey on or off (the mic stays untouched until you tap the key again).
async function toggleKeys($: EngineInterface, on?: boolean) {
  isKeysOn = on ?? !isKeysOn
  if (currentPhase === 'idle' || currentPhase === 'off' || currentPhase === 'muted') await setPhase($, rest())
  $.ui.toast(isKeysOn ? 'MYA: hotkey on' : 'MYA: hotkey off (Right Ctrl + Right Shift to turn it on)')
}

// One tap on the key: start listening, or, if already listening, finish (the text is then sent).
async function pressed($: EngineInterface, mode: Mode) {
  if (isSpeaking) stopSpeaking = true // a tap cuts MYA's voice, then we listen
  try {
    if (listening) await $.fs.write(stopFile, 'stop')
    else await listen($, mode, 'submit', 'hotkey')
  } catch (error) {
    listening = undefined
    await setPhase($, rest())
    $.ui.toast(`MYA: ${message(error)}`)
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
        '--keyterms', text('keyterms', 'Mya'),
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
    $.ui.toast(`MYA: ${problem || 'nothing received'}`)
    if (options.phrases !== false && text('voiceEngine', 'cartesia') === 'machine') void talk($, 'I did not hear you. Please, repeat.').catch(() => undefined)
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
      $.ui.toast(`MYA: translation failed (${done.reason})`)
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

// The language a Piper voice speaks, from its file name: "fr_FR-siwis-medium.onnx" -> French.
const piperLanguage = () => {
  const code = /^([a-z]{2})[_-]/.exec(text('piperModel').split('/').pop() ?? '')?.[1] ?? text('language', 'en')
  return LANGUAGES[code] ?? code
}

// MYA reads Claude's reply aloud. A machine or Piper voice speaks ONE language (a French voice reading English is unintelligible), so the
// reply is first turned into a short spoken message in that language; a human-like cloud voice only condenses a long reply.
async function say($: EngineInterface, answer: string) {
  const engine = text('voiceEngine', 'cartesia')
  const isMachine = engine === 'machine'
  const voiceLanguage = isMachine ? machineLanguage() : engine === 'piper' ? piperLanguage() : undefined
  let spoken = answer
  const isPlainAscii = !/[^\x00-\x7f]/.test(answer)
  // A machine voice speaks short plain ASCII as it is; Piper cannot tell the language of a text, so it always goes through the model.
  if (isMachine ? !(isPlainAscii && answer.length <= 350) : voiceLanguage ? true : answer.length > 350) {
    const language = voiceLanguage ? `in ${voiceLanguage}` : 'in the same language'
    const short = await $.model.complete({
      model: 'haiku',
      prompt:
        `Here is a coding assistant's reply to the user. Turn it into a short spoken message ${language}: ` +
        (voiceLanguage ? `the message MUST be written entirely ${language}, translating anything that is in another language (keep only names of files or tools as they are). ` : '') +
        '2 to 4 short plain sentences, one idea each, with commas where a speaker would pause, like an old computer reading carefully; ' +
        'no markdown, no code, no paths or commands to spell out, no abbreviations or symbols ' +
        'a speech synthesizer would stumble on. Give the gist, and say clearly if the user has to do something. ' +
        'Reply with the message only.\n<r>' + answer.slice(0, 6000) + '</r>',
    })
    if (short.isAnswered) spoken = short.text
    else if (voiceLanguage) {
      $.ui.toast('MYA: could not prepare the spoken message')
      return
    }
  }
  await talk($, spoken)
}

// Speaks one text aloud with MYA's voice, showing the 'speaking' phase and honouring a tap that cuts it off.
async function talk($: EngineInterface, spoken: string) {
  isSpeaking = true
  stopSpeaking = false
  await setPhase($, 'speaking')
  try {
    const voice = $.process.spawn({
      argv: [
        python(), `${root}/bin/speak.py`,
        ...envFileArgs(),
        '--engine', text('voiceEngine', 'cartesia'),
        '--piper-model', text('piperModel'),
        '--machine-voice', text('machineVoice', 'en-us+klatt4'),
        '--machine-rate', String(Number(options.machineRate ?? 155)),
        '--machine-wordgap', String(Number(options.machineWordGap ?? 4)),
        '--language', text('language', 'en'),
        '--voice', text('voiceId'),
        '--style', text('voiceStyle', 'plain'),
        '--speed', String(Number(options.voiceSpeed ?? 1)),
        '--device', text('speakerDevice', 'default'),
      ],
      env: keysEnv(),
      input: spoken,
    })
    for await (const piece of voice) {
      if (stopSpeaking) break // leaving the loop stops playback
      if (piece.stream === 'stdout' && piece.text.startsWith('ERR')) $.ui.toast(`MYA: ${piece.text.split('\t')[1] ?? ''}`)
    }
  } finally {
    isSpeaking = false
    stopSpeaking = false
    if (!listening) await setPhase($, rest())
  }
}

// The phone: a bell now and then while Claude waits for you.
function ring($: EngineInterface) {
  if (options.ringSound !== true) return
  void (async () => {
    try {
      const bell = $.process.spawn({
        argv: [python(), `${root}/bin/ring.py`, '--times', '2', '--device', text('speakerDevice', 'default')],
      })
      for await (const _piece of bell) { /* plays to the end */ }
    } catch { /* a missing bell is not worth an error */ }
  })()
}

const LABEL: Record<Phase, string> = {
  off: 'hotkey off, Right Ctrl + Right Shift or /mya on',
  waiting: 'your turn, tap Right Ctrl to answer',
  idle: 'tap Right Ctrl to talk',
  listening: 'listening, tap Right Ctrl to send',
  translating: 'translating, tap Right Ctrl to send',
  thinking: 'thinking',
  speaking: 'speaking, tap Right Ctrl to interrupt',
  muted: 'muted (/mya mute)',
}
const COLOR: Record<Phase, string> = { off: 'red', waiting: 'yellow', idle: 'gray', listening: 'green', translating: 'yellow', thinking: 'magenta', speaking: 'cyan', muted: 'gray' }
const BARS = '▁▂▃▄▅▆▇█'
// A telephone that rings: the handset rocks and the sound waves come and go.
const PHONE = ['  ☎  ', ' ((☎)) ', '(((☎)))', ' ((☎)) ']
const phone = (tick: number) => PHONE[tick % PHONE.length]!

// A little level meter that moves while MYA listens or speaks.
const meter = (tick: number, width = 12) =>
  Array.from({ length: width }, (_, i) => BARS[Math.min(7, Math.floor(Math.abs(Math.sin(tick * 0.9 + i * 1.7)) * 8))]).join('')

export const register: Register = (on, config) => {
  options = config
  isKeysOn = options.hotkeyOnStart !== false

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (isVoiceTurn && !e.agentId) {
      isVoiceTurn = false
      const willSpeak = options.speakReplies !== false && !isMuted && e.reason === 'answer' && e.answer.trim() !== ''
      if (willSpeak) {
        void say($, e.answer)
          .catch(error => $.ui.toast(`MYA: ${message(error)}`))
          .finally(() => { void waitForYou($, e.reason === 'answer') })
        return done
      }
    }
    if (!e.agentId) await waitForYou($, e.reason === 'answer')
    return done
  })

  on('prompt.submit', async ($, e, next) => {
    if (!listening) await setPhase($, 'thinking')
    return next(e)
  })

  on('session.start', async ($, e, next) => {
    root = $.plugin.root
    await $.command.register({
      name: 'mya',
      description: 'MYA voice: /mya (dictate into the prompt), /mya go (dictate and send), /mya stop, /mya mute, /mya off|on (the Right Ctrl hotkey).',
    })

    if (options.phrases !== false && text('voiceEngine', 'cartesia') === 'machine') {
      void talk($, 'Mya online. I am ready, when you are.').catch(() => undefined)
    }
    await setPhase($, rest())
    ticker?.cancel()
    ticker = $.clock.every(300, () => {
      if (currentPhase !== 'idle' && currentPhase !== 'muted' && currentPhase !== 'off') void update($, frame, n => (n ?? 0) + 1) // the band animates
    })

    // The hotkey: tap = dictate / send, with the chord key held = translate.
    void (async () => {
      try {
        const keys = $.process.spawn({
          argv: [python(), `${root}/bin/hotkey.py`, String(options.toggleKeycode ?? 105), String(options.chordKeycode ?? 65), String(options.lockKeycode ?? 62), String(options.maxTapSeconds ?? 0.8)],
        })
        for await (const piece of keys) {
          if (piece.stream !== 'stdout') continue
          for (const line of piece.text.split('\n')) {
            const [word, ...parts] = line.trim().split('\t')
            if (word === 'LOCK') void toggleKeys($)
            else if (word === 'TOGGLE' && isKeysOn) void pressed($, 'dictate')
            else if (word === 'TRANSLATE' && isKeysOn) void pressed($, 'translate')
            else if (word === 'ERR') $.ui.toast(`MYA: hotkey ${parts.join(' ')}`)
          }
        }
      } catch {
        $.ui.toast('MYA: the hotkey is unavailable')
      }
    })()

    return next(e)
  })

  on('command.run', { command: 'mya' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    if (arg === 'stop') {
      if (!listening) return { text: 'MYA is not listening.' }
      await $.fs.write(stopFile, 'stop')
      return { text: 'MYA: finishing…' }
    }
    if (arg === 'off' || arg === 'on' || arg === 'keys') {
      await toggleKeys($, arg === 'keys' ? undefined : arg === 'on')
      return { text: isKeysOn ? 'MYA hotkey is on.' : 'MYA hotkey is off: Right Ctrl does nothing until /mya on, or Right Ctrl + Right Shift.' }
    }
    if (arg === 'mute') {
      isMuted = !isMuted
      if (isMuted) stopSpeaking = true
      if (currentPhase === 'idle' || currentPhase === 'muted') await setPhase($, rest())
      return { text: isMuted ? 'MYA will stay quiet.' : 'MYA will speak again.' }
    }
    if (arg !== '' && arg !== 'go') return { text: 'Usage: /mya, /mya go, /mya stop, /mya mute, /mya off or /mya on.' }
    if (listening) return { text: 'MYA is already listening: speak, or /mya stop.' }
    void listen($, 'dictate', arg === 'go' ? 'submit' : 'fill', 'command').catch(async error => {
      listening = undefined
      await setPhase($, rest())
      $.ui.toast(`MYA: ${message(error)}`)
    })
    return { text: 'MYA is listening…' }
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
        <Text bold inverse color={color}> MYA </Text>
        <Text color={color}> {live ? meter(tick) : now === 'thinking' ? dots.padEnd(3) : now === 'waiting' ? phone(tick) : '·'} </Text>
        <Text dimColor>{isKeysOn || now === 'off' ? LABEL[now] : LABEL[now].replace(/, tap Right Ctrl.*$/, '')}</Text>
      </Box>
    )
  })
}
