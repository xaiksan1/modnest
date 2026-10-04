# IGOR

A robot voice for [Claude Code](https://code.claude.com), as a mod (a plugin of function hooks): the voice of a 1990s computer, in your terminal.

- **Tap Right Ctrl** → speak → **tap again**: your words are transcribed and sent to Claude.
- **Right Ctrl + Space** → speak → tap: your words are transcribed, **translated** (default: into English) and sent.
- A one-line **IGOR band** above the prompt shows what it is doing: listening (with a moving level meter), thinking, speaking, and, when Claude has finished and waits for you, a **ringing telephone** (with an optional old-fashioned bell: `ringSound`).
- IGOR has a few lines of its own: a greeting when the session starts and a line when it did not hear you (`phrases`).
- When you sent the question by voice, **IGOR reads Claude's answer aloud** with a real machine voice: eSpeak NG, a formant synthesizer in the spirit of 1990s computers, rendered locally (no key, no network). A machine voice speaks one language (English by default), so the reply is first turned into a short spoken message in that language. A human-like cloud voice (Cartesia) with an optional robot effect is available as `voiceEngine: cartesia`. Long answers are first condensed into a few spoken sentences; code and paths are not read out. Tap the key while Claude talks to cut it off and start your next question.
- `/igor` fills the prompt instead of sending (`/igor go` sends, `/igor stop` ends a recording, `/igor mute` toggles speech).

## Requirements

- **Linux with an X11 session** (not Wayland, macOS or Windows: the hotkey is read with `xinput`).
- `arecord` and `aplay` (alsa-utils), `xinput`, `libespeak-ng` (the machine voice; it ships with `speech-dispatcher`), `ffmpeg` (only for the optional Cartesia robot effect), Python 3 (standard library only, nothing to `pip install`).
- A [Deepgram](https://deepgram.com) API key for speech-to-text. Optional: a [Cartesia](https://cartesia.ai) API key, only for the cloud voice.

## Install

```bash
claude --plugin-dir mods/igor
```

Then set your keys, either in the plugin's options (`/config`, stored in secure storage) or in your shell environment (`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`). **Never put keys in a file you commit.** Set `language` to what you speak (`en`, `fr`, `es`, `de`...) and `translateTo` to the language you want for Right Ctrl + Space.

## Options

| Option | Default | Meaning |
|---|---|---|
| `language` | `en` | Deepgram language code of what you say; also the speech language of replies |
| `keyterms` | `Igor` | Comma-separated names Deepgram should favour (and that common mishearings are corrected to) |
| `translateTo` | `English` | Target language of the translate chord |
| `speakReplies` | `true` | Read answers aloud when the question was voiced |
| `voiceEngine` | `machine` | `machine` (eSpeak NG, local) or `cartesia` (human-like cloud voice) |
| `machineVoice` | `en-us+klatt4` | eSpeak NG voice and variant (`fr+klatt`, `en+m3`...); replies are turned into this voice's language before speaking |
| `voiceStyle` | `robot` | `robot` (buzzing 90s computer), `soft` (grit only) or `plain` (no effect) |
| `machineRate` / `machineWordGap` | `155` / `4` | Rhythm of the machine voice: words per minute and the pause between words |
| `ringSound` | `false` | Play a telephone bell when it is your turn |
| `phrases` | `true` | IGOR's own spoken lines |
| `voiceSpeed` | `0.9` | Speaking speed from 0.5 (slow) to 2.0 (fast); some voices talk fast |
| `voiceId` | _(empty)_ | Cartesia voice id; empty = Henry, a flat male voice |
| `showBand` | `true` | Show the IGOR band above the prompt |
| `micDevice` | `auto` | ALSA capture device (`auto` prefers a USB microphone; see `arecord -l`) |
| `speakerDevice` | `default` | ALSA playback device |
| `python` | `python3` | Python 3 command for the helpers |
| `toggleKeycode` / `chordKeycode` | `105` / `65` | X11 keycodes (Right Ctrl / Space; list yours with `xmodmap -pke`) |

## What it sends where (read this)

- Your **microphone audio** goes to Deepgram while you record.
- With the default machine voice, **nothing is sent for speech**. With `voiceEngine: cartesia`, the text of Claude's answer (or its condensed version) goes to Cartesia.
- Translation and condensing use a small `haiku` call through your Claude Code session. The robot effect runs locally with ffmpeg.
- The hotkey helper reads every X11 key event with `xinput test-xi2 --root` and **keeps only Right Ctrl and the chord key**; all other keys are dropped on the spot, nothing is stored or written. Read `bin/hotkey.py` (about 60 lines) before enabling it.

## Known limits

- The chord's Space also reaches the terminal as Ctrl+Space.
- Recording is manual: it ends when you tap the key again (or after three minutes).
- X11 only. Not tested on other desktops or distributions.

## Tests

```bash
claude plugin validate mods/igor
claude plugin test mods/igor
```
