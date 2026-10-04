# voice-input

Hands-free voice for [Claude Code](https://code.claude.com), as a mod (a plugin of function hooks).

- **Tap Right Ctrl** → speak → **tap again**: your words are transcribed and sent to Claude.
- **Right Ctrl + Space** → speak → tap: your words are transcribed, **translated** (default: into English) and sent.
- When you sent the question by voice, **Claude's answer is read aloud**. Long answers are first condensed into a few spoken sentences; code and paths are not read out. Tap the key while Claude talks to cut it off and start your next question.
- `/voice` fills the prompt instead of sending (`/voice go` sends, `/voice stop` ends a recording, `/voice mute` toggles speech).

## Requirements

- **Linux with an X11 session** (not Wayland, macOS or Windows: the hotkey is read with `xinput`).
- `arecord` and `aplay` (alsa-utils), `xinput`, Python 3 (standard library only, nothing to `pip install`).
- A [Deepgram](https://deepgram.com) API key for speech-to-text. Optional: a [Cartesia](https://cartesia.ai) API key to hear replies.

## Install

```bash
claude --plugin-dir mods/voice-input
```

Then set your keys, either in the plugin's options (`/config`, stored in secure storage) or in your shell environment (`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`). **Never put keys in a file you commit.** Set `language` to what you speak (`en`, `fr`, `es`, `de`...) and `translateTo` to the language you want for Right Ctrl + Space.

## Options

| Option | Default | Meaning |
|---|---|---|
| `language` | `en` | Deepgram language code of what you say; also the speech language of replies |
| `translateTo` | `English` | Target language of the translate chord |
| `speakReplies` | `true` | Read answers aloud when the question was voiced |
| `voiceId` | _(empty)_ | Cartesia voice id; empty = a default library voice |
| `micDevice` | `auto` | ALSA capture device (`auto` prefers a USB microphone; see `arecord -l`) |
| `speakerDevice` | `default` | ALSA playback device |
| `python` | `python3` | Python 3 command for the helpers |
| `toggleKeycode` / `chordKeycode` | `105` / `65` | X11 keycodes (Right Ctrl / Space; list yours with `xmodmap -pke`) |

## What it sends where (read this)

- Your **microphone audio** goes to Deepgram while you record.
- The **text of Claude's answer** (or its condensed version) goes to Cartesia when replies are spoken.
- Translation and condensing use a small `haiku` call through your Claude Code session.
- The hotkey helper reads every X11 key event with `xinput test-xi2 --root` and **keeps only Right Ctrl and the chord key**; all other keys are dropped on the spot, nothing is stored or written. Read `bin/hotkey.py` (about 60 lines) before enabling it.

## Known limits

- The chord's Space also reaches the terminal as Ctrl+Space.
- Recording is manual: it ends when you tap the key again (or after three minutes).
- X11 only. Not tested on other desktops or distributions.

## Tests

```bash
claude plugin validate voice-input
claude plugin test voice-input
```
