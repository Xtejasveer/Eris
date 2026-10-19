> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Python SDK — Text-to-Speech

> Synthesize speech with the REST, SSE, and realtime WebSocket clients.

## Overview

The SDK exposes three TTS clients — one per transport. They accept identical arguments and produce identical audio; they differ only in how quickly the first bytes reach you.

| Class | Transport | Style | Use it for |
| - | - | - | - |
| `GnaniTTSClient` | REST | sync | Batch jobs, short strings, anything written to a file |
| `GnaniTTSStreamClient` | SSE | sync generator | Progressive playback without `asyncio` |
| `GnaniTTSRealtimeClient` | WebSocket | `async` | Conversational agents, lowest time-to-first-audio |

```python theme={null}
from gnani.tts import GnaniTTSClient, GnaniTTSStreamClient, GnaniTTSRealtimeClient
```

<Warning>
  Always pass `model="timbre-v2.5"`. The SDK's built-in default is still `timbre-v2.0`, which the API no longer serves — a call without an explicit `model` fails with `400` and `The supported models are "timbre-v2.5"`. Every example on this page sets it explicitly.
</Warning>

***

## REST — single response

Returns the complete audio as `bytes`. Pass `output_file` to also write it to disk; parent directories are created for you.

```python theme={null}
from gnani.tts import GnaniTTSClient

client = GnaniTTSClient()   # or GnaniTTSClient(api_key="your-api-key")

audio = client.synthesize(
    "नमस्ते, आप कैसे हैं?",
    voice="Nalini",
    model="timbre-v2.5",
    language="hi-IN",
    output_file="output.wav",
)

print(len(audio), "bytes")
```

Without `output_file`, handle the bytes yourself — upload them, return them from a web handler, or push them into an audio device.

```python theme={null}
audio = client.synthesize("Hello there", voice="Pranav", model="timbre-v2.5", language="en-IN")
return Response(audio, mimetype="audio/wav")
```

### Parameters

Shared by all three clients unless noted.

| Parameter | Type | Default | Description |
| - | - | - | - |
| `text` | `str` | *required* | The text to synthesize. |
| `voice` | `str` | `"Pranav"` | Voice ID. See [Voices](#voices). Ignored when `speaker_embedding` is given. |
| `model` | `str` | `"timbre-v2.0"` | **Set to `"timbre-v2.5"`.** |
| `language` | `str` | `None` | BCP-47 code. `timbre-v2.5` only. |
| `speed` | `float` | `1.0` | Speaking rate, `0.85`–`1.15`. `timbre-v2.5` only. |
| `audio_config` | `AudioConfig` | 48 kHz WAV | Output format. See [Audio configuration](#audio-configuration). |
| `speaker_embedding` | `SpeakerEmbedding` | `None` | Cloned voice. See [Voice cloning](#voice-cloning). |
| `output_file` | `str \| Path` | `None` | Write the audio here. Not available on `synthesize_stream()` / `synthesize()` on the realtime client. |
| `request_id` | `str` | auto | Custom ID for tracing. |

Invalid combinations raise `ValueError` locally — an unknown voice for the model, `speed` out of range, or `language`/`speed` passed with a non-`timbre-v2.5` model.

***

## SSE — progressive playback

`synthesize_stream()` yields raw PCM chunks as they are generated, so playback can start before synthesis finishes. Chunks carry **no WAV header**.

```python theme={null}
from gnani.tts import GnaniTTSStreamClient

client = GnaniTTSStreamClient()

for chunk in client.synthesize_stream(
    "Your order has been confirmed and will arrive tomorrow.",
    voice="Kaveri",
    model="timbre-v2.5",
    language="en-IN",
):
    player.write(chunk)     # feed your audio device as bytes arrive
```

If you want a finished file instead, `synthesize()` collects every chunk and adds a RIFF header when the output is linear PCM WAV:

```python theme={null}
audio = client.synthesize(
    "Your order has been confirmed.",
    voice="Kaveri",
    model="timbre-v2.5",
    language="en-IN",
    output_file="confirmation.wav",
)
```

<Note>
  The header is added only for `encoding="linear_pcm"` with `container="wav"`. For `mp3`, `oggopus`, or telephony encodings, the server's bytes are returned untouched — those formats carry their own framing.
</Note>

***

## Realtime WebSocket — lowest latency

`GnaniTTSRealtimeClient` is `async` and offers three shapes, depending on how much control you need.

<Tabs>
  <Tab title="Stream chunks">
    `synthesize()` is an async generator of audio bytes. Use it when audio should start playing immediately.

    ```python theme={null}
    import asyncio

    from gnani.tts import GnaniTTSRealtimeClient


    async def main():
        async with GnaniTTSRealtimeClient() as client:
            async for chunk in client.synthesize(
                "नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?",
                voice="Nalini",
                model="timbre-v2.5",
                language="hi-IN",
            ):
                await player.feed(chunk)


    asyncio.run(main())
    ```
  </Tab>

  <Tab title="Collect to a file">
    `synthesize_and_collect()` waits for the full response and returns it, with a WAV header when the output is linear PCM WAV.

    ```python theme={null}
    import asyncio

    from gnani.tts import GnaniTTSRealtimeClient


    async def main():
        async with GnaniTTSRealtimeClient() as client:
            audio = await client.synthesize_and_collect(
                "नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?",
                voice="Nalini",
                model="timbre-v2.5",
                language="hi-IN",
                output_file="reply.wav",
            )


    asyncio.run(main())
    ```
  </Tab>

  <Tab title="Typed events">
    `synthesize_events()` yields typed events instead of bare bytes, so you can read `chunk_index`, detect the final chunk, and log the server's `request_id`.

    ```python theme={null}
    import asyncio

    from gnani.tts import (
        GnaniTTSRealtimeClient,
        TTSAudioChunkEvent,
        TTSCompletedEvent,
        TTSStartEvent,
    )


    async def main():
        async with GnaniTTSRealtimeClient() as client:
            async for event in client.synthesize_events(
                "Your order has been confirmed.",
                voice="Pranav",
                model="timbre-v2.5",
                language="en-IN",
            ):
                if isinstance(event, TTSStartEvent):
                    print(f"started — {event.request_id}")
                elif isinstance(event, TTSAudioChunkEvent):
                    await player.feed(event.data)
                    if event.is_final:
                        print("last audio chunk")
                elif isinstance(event, TTSCompletedEvent):
                    print(f"done — {event.total_chunks} chunks")


    asyncio.run(main())
    ```
  </Tab>
</Tabs>

### Events

<ResponseField name="TTSStartEvent" type="dataclass">
  The server has begun streaming audio.

  <Expandable title="Attributes">
    <ResponseField name="request_id" type="str">Identifier for this TTS request.</ResponseField>
    <ResponseField name="message" type="str">Status message from the server.</ResponseField>
  </Expandable>
</ResponseField>

<ResponseField name="TTSAudioChunkEvent" type="dataclass">
  One binary audio chunk.

  <Expandable title="Attributes">
    <ResponseField name="data" type="bytes">Raw audio bytes for this chunk.</ResponseField>
    <ResponseField name="chunk_index" type="int">Zero-based index within the response.</ResponseField>
    <ResponseField name="is_final" type="bool">`True` on the last audio-bearing chunk.</ResponseField>
  </Expandable>
</ResponseField>

<ResponseField name="TTSCompletedEvent" type="dataclass">
  Synthesis is finished and the connection is closing.

  <Expandable title="Attributes">
    <ResponseField name="request_id" type="str">Identifier for this TTS request.</ResponseField>
    <ResponseField name="total_chunks" type="int">Number of audio chunks sent.</ResponseField>
  </Expandable>
</ResponseField>

<Note>
  Each call to `synthesize()`, `synthesize_events()`, or `synthesize_and_collect()` opens its own WebSocket connection and closes it when the server finishes. The `async with` block is for symmetry and future-proofing — it does not pool connections, so reusing one client instance across many calls is safe and cheap.
</Note>

***

## Audio configuration

`AudioConfig` controls the output format. The default is 48 kHz, 16-bit mono WAV.

```python theme={null}
from gnani.tts import AudioConfig, GnaniTTSClient

client = GnaniTTSClient()

audio = client.synthesize(
    "Your order has been confirmed.",
    voice="Pranav",
    model="timbre-v2.5",
    language="en-IN",
    audio_config=AudioConfig(sample_rate=48000, container="mp3", bitrate="128k"),
    output_file="confirmation.mp3",
)
```

| Field | Type | Default | Accepted values |
| - | - | - | - |
| `sample_rate` | `int` | `48000` | `8000`, `16000`, `22050`, `24000`, `44100`, `48000` |
| `encoding` | `str` | `"linear_pcm"` | `linear_pcm`, `oggopus`, `pcm_mulaw`, `pcm_alaw` |
| `num_channels` | `int` | `1` | `1`–`8` |
| `sample_width` | `int` | `2` | `1`–`4` (bytes per sample) |
| `container` | `str` | `"wav"` | `raw`, `wav`, `mp3`, `ogg`, `mulaw`, `alaw` |
| `bitrate` | `str` | `None` | `32k`, `64k`, `96k`, `128k`, `192k` — MP3 only |

### Common presets

<CodeGroup>
  ```python Web playback (WAV) theme={null}
  AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav")
  ```

  ```python Compressed download (MP3) theme={null}
  AudioConfig(sample_rate=48000, container="mp3", bitrate="128k")
  ```

  ```python Telephony (µ-law, 8 kHz) theme={null}
  AudioConfig(sample_rate=8000, encoding="pcm_mulaw", container="mulaw")
  ```

  ```python Telephony (A-law, 8 kHz) theme={null}
  AudioConfig(sample_rate=8000, encoding="pcm_alaw", container="alaw")
  ```

  ```python Opus theme={null}
  AudioConfig(encoding="oggopus", container="raw")
  ```
</CodeGroup>

Unsupported values raise `ValueError` before the request is sent.

***

## Voices

`timbre-v2.5` offers 42 voices. Each has a preferred language — match `voice` to `language` for best quality.

| Language | `language` | Voices |
| :- | :- | :- |
| English | `en-IN` | Kaveri, Trupti, Devika, Pranav, Shlok, Girish |
| Hindi | `hi-IN` | Nalini, Bhavna, Yashvi, Urmila, Jwala, Chitra, Ambuja, Deepak, Roopesh, Vikrant, Hemraj, Jalaj, Omkar |
| Tamil | `ta-IN` | Asmita, Trisha, Brinda, Vedika, Noopur |
| Telugu | `te-IN` | Suhana, Lehara, Lavanya, Yukti, Varuni |
| Kannada | `kn-IN` | Saanvi, Kavin |
| Malayalam | `ml-IN` | Reshma, Riyaan |
| Marathi | `mr-IN` | Zahira, Ishaan |
| Bengali | `bn-IN` | Kirra, Dhruva |
| Gujarati | `gu-IN` | Falak, Veera |
| Punjabi | `pa-IN` | Mehuli, Zayan |
| Hinglish | `auto` | Poorvi |

Query the list at runtime rather than hard-coding it:

```python theme={null}
from gnani.tts import GnaniTTSClient

GnaniTTSClient.supported_voices("timbre-v2.5")
# ["Ambuja", "Asmita", "Bhavna", ...]
```

<Tip>
  Preview voices before integrating — open the [Gnani TTS playground](https://app.gnani.ai/voice/text-to-speech) and filter by language, gender, and persona. Full descriptions are in the [voice catalog](/api/TTS/available-voices).
</Tip>

### Language and speed

Both are `timbre-v2.5`-only. Passing either with another model raises `ValueError`.

```python theme={null}
audio = client.synthesize(
    "आपका ऑर्डर कन्फर्म हो गया है।",
    voice="Nalini",
    model="timbre-v2.5",
    language="hi-IN",
    speed=1.1,              # 0.85 – 1.15
)
```

Accepted `language` values: `auto`, `hi-IN`, `en-IN`, `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN`. Use `auto` to detect the language from the input script — this is also what the Hinglish voice expects.

***

## Voice cloning

Generate a speaker embedding with the [voice-clone embeddings endpoint](/api/VC/voice-clone-embeddings), then pass it as `SpeakerEmbedding`. When present, `voice` is ignored.

```python theme={null}
from gnani.tts import GnaniTTSClient, SpeakerEmbedding

embedding = SpeakerEmbedding(
    embedding=embedding_string,     # from POST /api/v1/tts/voice-clone/embeddings
    shape=[1, 768],
    dtype="torch.bfloat16",
)

audio = client.synthesize(
    "This is my cloned voice.",
    model="timbre-v2.5",
    speaker_embedding=embedding,
    output_file="cloned.wav",
)
```

`SpeakerEmbedding` works identically on all three clients.

***

## Error handling

```python theme={null}
from gnani.tts import GnaniTTSClient
from gnani.tts.exceptions import APIError, GnaniTTSError

client = GnaniTTSClient()

try:
    audio = client.synthesize(
        "Hello there",
        voice="Pranav",
        model="timbre-v2.5",
        language="en-IN",
    )
except APIError as exc:
    print(f"API returned {exc.status_code}: {exc.body}")
except GnaniTTSError as exc:
    print(f"SDK error: {exc}")
except ValueError as exc:
    print(f"Invalid parameters: {exc}")
```

| Exception | Raised when |
| - | - |
| `AuthenticationError` | No API key passed and `GNANI_API_KEY` unset. |
| `APIError` | Non-200 response. Carries `.status_code` and `.body`. |
| `StreamConnectionError` | The WebSocket handshake failed. |
| `StreamClosedError` | An operation was attempted on a closed stream. |
| `StreamError` | The server sent an error event mid-stream. |
| `ValueError` | Invalid voice, model, sample rate, container, bitrate, or speed — raised locally, before any request. |

All except `ValueError` inherit from `GnaniTTSError`.

***

## Further Reading

* [Python SDK overview](/python-sdk/introduction) — installation, auth, client selection
* [Python SDK — Speech-to-Text](/python-sdk/speech-to-text)
* [Available Voices](/api/TTS/available-voices) — full catalog with personas
* [TTS REST](/api/TTS/tts-inference) · [TTS SSE](/api/TTS/tts-sse) · [TTS Realtime](/api/TTS/tts-websocket) — endpoint references
* [Text Formatting](/api/TTS/tts-input-formating) — pauses, numbers, and pronunciation control


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.