> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Introduction – Gnani Speech APIs

> Speech-to-text, text-to-speech, and voice cloning APIs for Indian languages — REST, streaming, and batch.

Build with Gnani Speech APIs when you need transcription or synthesis in production — REST for short clips, WebSocket for live audio, and Batch for long or multi-file jobs.

| Product | When to use it |
| - | - |
| **This section** | Integrate STT, TTS, or voice cloning directly in your app |
| [Agent Builder](/introduction) | Configure agents in the console |
| [Agent Builder Platform API](/Platform/platform-introduction) | Manage agents, FAQs, and conversations over REST |

## Base URL

```text theme={null}
https://api.vachana.ai
```

All paths in this documentation are relative to this base URL.

## Authentication

Send your API key on every request:

```bash theme={null}
X-API-Key-ID: <your_api_key>
```

Generate a key from the [Gnani API dashboard](https://app.gnani.ai/voice). Missing or invalid keys return `401 Unauthorized`.

<Tip>
  Store keys in environment variables or a secrets manager. Do not commit them to source control.
</Tip>

## Available APIs

### Speech-to-Text — Gnani Prisma v2.5

| API | Best for | Guide |
| - | - | - |
| STT REST | Audio up to 60 seconds, single HTTP response | [Speech-to-Text REST](/api/STT/speech-to-text) |
| STT Realtime | Live microphone or streaming audio | [STT Realtime](/api/STT/stt-websocket) |
| STT Batch | Long files, many files, offline pipelines | [Batch STT](/api/STTBatch/Introduction) |

### Text-to-Speech — Gnani Timbre v2.5

<Tip>
  Timbre v2.5 is the recommended model. Timbre v2.0 is deprecated and will be removed in a future release.
</Tip>

| API | Best for | Guide |
| - | - | - |
| TTS REST | Full audio in one response | [TTS REST](/api/TTS/tts-inference) |
| TTS Streaming | Progressive playback via SSE | [TTS Streaming](/api/TTS/tts-sse) |
| TTS Realtime | Lowest latency over WebSocket | [TTS Realtime](/api/TTS/tts-websocket) |
| Voice catalog | Pick a voice before you integrate | [Available Voices](/api/TTS/available-voices) |

### Voice cloning

| API | Best for | Guide |
| - | - | - |
| VC Embeddings | Create a `speaker_embedding` from reference audio | [Voice Clone Embeddings](/api/VC/voice-clone-embeddings) |
| VC REST | Cloned voice in one HTTP response | [VC REST](/api/VC/vc-inference) |
| VC Streaming | Cloned voice over SSE | [VC Streaming](/api/VC/vc-sse) |
| VC Realtime | Cloned voice over WebSocket | [VC Realtime](/api/VC/vc-websocket) |

## Key capabilities

| Capability | Details |
| - | - |
| Languages | 10+ Indian languages with native-script output |
| Audio formats | WAV, MP3, OGG, FLAC, AAC, M4A (STT) |
| Voice cloning | Clone from a short reference sample |
| Latency | P95 \~200 ms for STT; streaming TTS supported |
| Modes | Real-time, REST, and batch |
| Formatting | Auto-punctuation and text normalization on supported endpoints |
| SSML | Supported on TTS for fine-grained control |

## Integrations

| Plugin | Guide |
| - | - |
| LiveKit | [LiveKit plugin](/livekit/introduction) |
| Pipecat | [Pipecat plugin](/pipecat/introduction) |

## Use case guides

| Guide | Description |
| - | - |
| [Podcast transcription](/api/use-cases/podcast-transcription) | Speaker-separated batch transcription |
| [Call analytics](/api/use-cases/call-analytics) | Batch STT plus LLM analysis |
| [Real-time compliance](/api/use-cases/real-time-compliance) | Live WebSocket monitoring |

## Get started

New to the APIs? Start here: [Quick Start](/api/introduction/quick-start)

***

## Docs feedback

Docs feedback: [Gnani APIs docs feedback](https://discord.com/channels/1511338519899930634/1515991436229611571)

**Last verified:** 5 August 2026


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.