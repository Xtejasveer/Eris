# Talking avatar: investigation and plan

## 1. What exists today (findings)

| Question | Finding |
|---|---|
| TTS | **Gnani Timbre v2.5** (`eris/classroom/voice.py`), called by the backend. A browser fallback (`speechSynthesis`) is used when there is no Gnani key or a clip fails. |
| How audio reaches the client | **One full WAV file per spoken line**, over plain HTTP: `POST /api/tts` → `FileResponse(audio/wav)`. No WebSocket, no streaming. Clips are cached on disk per line. |
| Format | **PCM16, mono, 48 000 Hz** WAV (checked on a real clip: 1 channel, 2-byte samples, 48 kHz). Our backend joins sentences into one clip with short silences between them. |
| Timestamps | **None.** Gnani's API and docs give no phoneme, viseme or word timings (no SSML either). The browser fallback voice *does* fire `boundary` events per word (Chrome, Safari, Edge; Firefox with some voices). |
| Frontend | Plain **ES modules, no framework, no build tool**. FastAPI serves `web/` as static files. |
| Playback | `web/js/voice.js`: the clip is fetched, turned into a blob URL, played by one `HTMLAudioElement`, which is already routed through a `MediaElementAudioSourceNode` → `AnalyserNode` → destination in **one AudioContext** (used for the "voice level" bars). The browser fallback voice is **not** routable through Web Audio. |
| Stop / interrupt | `Player.stop()` (Stop button, jumping to a section, leaving the page) calls `Voice.stop()`; Pause calls `Voice.pause()`. |

## 2. Library evaluation

**TalkingHead (MIT)** — not used as the engine, partly reused:
- It plays the audio itself (own AudioContext / playback worklet), needs a *full-body Mixamo rig*, and lip-syncs from
  **text + word/viseme timings**. It has no audio-driven lip sync, which is the mode this app needs (Gnani gives no
  timings). Bolting an audio-driven mode into its internal animation loop would be fragile.
- **Reused:** `lipsync-en.mjs` (MIT, English words → Oculus visemes, letter-to-sound rules) for the timestamp mode.

**HeadAudio (MIT code)** — not used: its trained model file (`model-en-mixed.bin`) has **no stated license**, which
fails the "permissive license for every asset" rule. Mode B is our own spectral classifier instead.

**Three.js 0.170.0 (MIT)** with `GLTFLoader` and the meshopt decoder (MIT), vendored under `web/vendor/three/`
(pinned, works offline, no CDN).

**Avatar:** TalkingHead's `mpfb.glb` — made with MPFB/MakeHuman, **CC0**. The other sample avatars there (Ready
Player Me, Avaturn, AvatarSDK, VRoid) are non-commercial only and are not used. It has 14 Oculus visemes (`sil` = rest)
and the ARKit set (jawOpen, blinks, eye looks, brows, smiles…), Head/Neck/Eye/Arm bones. Optimized with
gltf-transform (MIT, dev-only): textures 1024 px WebP, meshopt geometry — **36.8 MB → 3.15 MB**, all 8 meshes still
skinned, all blendshapes intact.

## 3. Plan

```
web/vendor/three/…                 three.js + GLTFLoader + meshopt decoder (MIT)
web/vendor/talkinghead/lipsync-en.mjs   (MIT)
web/assets/avatars/mpfb.glb        optimized CC0 avatar
web/js/avatar/
  audio-engine.js   one shared AudioContext, gesture unlock, gapless chunk queue, analyser on the output path
  scheduler.js      pure: PCM conversion, WAV parsing, gapless start-time math          (unit tested)
  lipsync.js        pure: audio features → viseme, envelope smoothing, word timings → visemes (unit tested)
  noise.js          pure: smooth 1-D noise for sway                                         (unit tested)
  life.js           blinks, saccades, head sway, breathing, nods, brows, mood
  avatar.js         createAvatar(): Three.js scene, camera, lights, morph mapping, render loop, events
web/avatar-demo.html                demo with debug overlay
tests/avatar/*.test.mjs             node --test, no dependencies
```

Stages (each one run and tested before the next): audio through the new pipeline → static model → audio-only lip
sync → idle life → timestamp mode → integration → demo, tests, README.

**Audio routing (never play twice):** `Voice` keeps one output `GainNode` in the shared AudioContext. Without the
avatar it goes to the speakers. With the avatar, the avatar takes that node as its input:
`voice bus → avatar gain → AnalyserNode → DelayNode → destination`. The analyser sits on the real output path.

**Lip sync modes (auto):**
- *Mode B, audio* (Gnani clips, chunked streams): every frame, RMS (with a noise gate) drives the jaw; spectral
  centroid, low/mid/high band energy and zero-crossing rate pick a viseme group (closed, open, spread, rounded,
  fricative), mapped to the 15 Oculus visemes.
- *Mode A, timings* (browser voice word boundaries, or `setTimestamps`): words → visemes with `lipsync-en`, scheduled
  on the clock and blended. If audio is also flowing, its energy still closes the mouth in silences.
- Both: asymmetric attack/release smoothing (~50 ms open, ~100 ms close), blending between visemes, clamped weights,
  delay compensation −150…+150 ms (positive = delay the audio, negative = delay the mouth).

## 4. Assumptions

- No streaming TTS exists today; `pushAudioChunk` is built and tested (demo streams 100 ms PCM chunks) so a future
  streaming TTS can use it, while the app uses `attachAudioStream` on the existing clip playback.
- The browser fallback voice cannot be analyzed (the Web Speech API exposes no audio), so it uses Mode A from word
  boundary events, with an estimated-duration fallback if a voice fires no boundaries.
- The avatar is on by default when it loads; it can be turned off (`AVATAR_ENABLED=false` in `.env`, or the toggle in
  the classroom), and the class then runs exactly as before (audio only).
- Firefox and Safari can't be run in this environment; the code uses only standard Web Audio / WebGL APIs and the iOS
  unlock pattern (resume on the first touch), but those browsers must be checked by hand.

## 5. Measured word timings (Gnani clips)

Gnani returns no timings, so they are measured: `eris/classroom/lip_timing.py` runs faster-whisper (`base.en`,
CPU, under a second per clip) for word times, matches them to the script's words, tightens each word to the voiced
audio and adds a per-word loudness. Without faster-whisper, or when too few words match, an energy aligner spreads
the words over the voiced frames. The result is cached as `<clip>.timing.json` (made by `render`, or on first use)
and served by `POST /api/tts/timing`.

The browser passes it to `avatar.setTimestamps(timing, { clock: "media", media: audioElement })`: the lips follow
the element's playback position minus the device's output latency (capped at 400 ms) plus a 40 ms lip lead, so
pause, resume and Bluetooth stay in sync. With clip timings the mouth stays shut between words (no analyser
gating, which runs ahead of what is heard), louder words open wider, "p/b/m" and "f/v" close fully and fast, and
the jaw opens per viseme (`JAW` in lipsync.js), never on closures. Before a clip's timings arrive, the audio-only
mode drives the lips as before. The demo page's "Play file with word timings" shows the same path.
