# MYA

A voice for [Claude Code](https://code.claude.com), as a mod (a plugin of function hooks): talk to your terminal, hear it answer, and see a phone ring when it is your turn.

- **Tap Right Ctrl** → speak → **tap again**: your words are transcribed and sent to Claude.
- **Right Ctrl + Space** → speak → tap: your words are transcribed, **translated** (default: into English) and sent.
- A one-line **MYA band** above the prompt shows what it is doing: listening (with a moving level meter), thinking, speaking, and, when Claude has finished and waits for you, a **ringing telephone** (with an optional old-fashioned bell: `ringSound`).
- MYA has a few lines of its own: a greeting when the session starts and a line when it did not hear you (`phrases`).
- When you sent the question by voice, **MYA reads Claude's answer aloud** with a human-like Cartesia voice (Katie by default). Long answers are first condensed into a few spoken sentences; code and paths are not read out. Three options for other tastes: an ffmpeg robot effect (`voiceStyle: robot`), a local formant synthesizer with no key and no network (`voiceEngine: machine`, eSpeak NG), or a free local neural voice (`voiceEngine: piper`, see below).
- **Hotkey on/off:** `/mya off` and `/mya on`, or **Right Ctrl + Right Shift**, switch the hotkey so it never fires while you copy-paste elsewhere (the band turns red and says so). A Ctrl held a while, or used with a key, a mouse click or the scroll wheel (Ctrl+C, Ctrl+click...), is never taken for a tap.
- `/mya` fills the prompt instead of sending (`/mya go` sends, `/mya stop` ends a recording, `/mya mute` toggles speech).

## Requirements

- **Linux with an X11 session** (not Wayland, macOS or Windows: the hotkey is read with `xinput`).
- `arecord` and `aplay` (alsa-utils), `xinput`, `ffmpeg` (only for the optional robot effect and the optional bell), `libespeak-ng` (only for the optional machine voice; it ships with `speech-dispatcher`), Python 3 (standard library only, nothing to `pip install`).
- A [Deepgram](https://deepgram.com) API key for speech-to-text. A [Cartesia](https://cartesia.ai) API key to hear replies (not needed with `voiceEngine: machine`).

## Install

```bash
claude --plugin-dir mods/mya
```

Then set your keys, either in the plugin's options (`/config`, stored in secure storage) or in your shell environment (`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`). **Never put keys in a file you commit.** Set `language` to what you speak (`en`, `fr`, `es`, `de`...) and `translateTo` to the language you want for Right Ctrl + Space.

## Options

| Option | Default | Meaning |
|---|---|---|
| `language` | `en` | Deepgram language code of what you say; also the speech language of replies |
| `keyterms` | `Mya` | Comma-separated names Deepgram should favour (and that common mishearings are corrected to) |
| `translateTo` | `English` | Target language of the translate chord |
| `speakReplies` | `true` | Read answers aloud when the question was voiced |
| `voiceEngine` | `cartesia` | `cartesia` (human-like cloud voice), `machine` (eSpeak NG, local) or `piper` (local neural voice) |
| `piperModel` | — | Piper engine only: path to a voice `.onnx` file (its `.onnx.json` beside it) |
| `machineVoice` | `en-us+klatt4` | Machine engine only: eSpeak NG voice and variant (`fr+klatt`, `en+m3`...) |
| `voiceStyle` | `plain` | Cartesia only: `plain`, `robot` (buzzing 90s computer) or `soft` (grit only) |
| `machineRate` / `machineWordGap` | `155` / `4` | Rhythm of the machine voice: words per minute and the pause between words |
| `ringSound` | `false` | Play a telephone bell when it is your turn |
| `phrases` | `true` | MYA's own spoken lines |
| `voiceSpeed` | `1.0` | Speaking speed from 0.5 (slow) to 2.0 (fast); lower it if a voice talks too fast |
| `voiceId` | _(empty)_ | Cartesia voice id; empty = MYA's original voice (Katie) |
| `showBand` | `true` | Show the MYA band above the prompt |
| `micDevice` | `auto` | ALSA capture device (`auto` prefers a USB microphone; see `arecord -l`) |
| `speakerDevice` | `default` | ALSA playback device |
| `python` | `python3` | Python 3 command for the helpers |
| `toggleKeycode` / `chordKeycode` / `lockKeycode` | `105` / `65` / `62` | X11 keycodes: Right Ctrl, Space (translate), Right Shift (hotkey on/off); list yours with `xmodmap -pke` |
| `maxTapSeconds` | `0.8` | A dictation key held longer than this is not a tap |
| `hotkeyOnStart` | `true` | Whether the hotkey is active when the session starts |

## What it sends where (read this)

- Your **microphone audio** goes to Deepgram while you record.
- The **text of Claude's answer** (or its condensed version) goes to Cartesia when replies are spoken. With `voiceEngine: machine` nothing is sent for speech.
- Translation and condensing use a small `haiku` call through your Claude Code session. The robot effect runs locally with ffmpeg.
- The hotkey helper reads every X11 key and mouse-button event with `xinput test-xi2 --root` and **keeps only Right Ctrl and its two chord keys**; everything else is dropped on the spot, nothing is stored or written. Read `bin/hotkey.py` (about 60 lines) before enabling it.

## Known limits

- The chord's Space also reaches the terminal as Ctrl+Space.
- Recording is manual: it ends when you tap the key again (or after three minutes).
- X11 only. Not tested on other desktops or distributions.

## Tests

```bash
claude plugin validate mods/mya
claude plugin test mods/mya
```

## Optional: a free local voice with Piper

No account, no credit, no network. Piper is a separate project under the GPL-3.0 licence; MYA does **not** bundle it, you install it yourself, for the Python you give MYA in the `python` option:

```bash
python -m pip install piper-tts                               # installs piper-tts and pathvalidate
python -m piper.download_voices --download-dir ~/.local/share/piper fr_FR-siwis-medium
```

Then set `voiceEngine: piper`, `piperModel: ~/.local/share/piper/fr_FR-siwis-medium.onnx` (full path) and `python` to that interpreter. Sentences are synthesized one after the other and streamed into a single `aplay`, so playback does not stop between sentences as long as synthesis is faster than speech (about 5x on a modest CPU in our test).
