> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Python SDK

> Official Python client for Gnani Speech-to-Text and Text-to-Speech across REST, SSE, and WebSocket.

## Overview

`gnani-vachana` is the official Python client for the Gnani Speech APIs. It wraps STT and TTS across all three transports — REST, SSE, and WebSocket — plus batch transcription jobs, so you never hand-roll multipart uploads, SSE frame parsing, WAV headers, or WebSocket lifecycles.

```text theme={null}
gnani-vachana              ← pip install name
  └── gnani                ← import name
        ├── gnani.stt      → GnaniSTTClient (REST) · GnaniSTTStreamClient (WebSocket)
                             GnaniSTTBatchClient · AsyncGnaniSTTBatchClient (batch jobs)
        └── gnani.tts      → GnaniTTSClient (REST) · GnaniTTSStreamClient (SSE)
                             GnaniTTSRealtimeClient (WebSocket)
```

The package is dependency-light — `requests` and `websockets` only — ships type hints (`py.typed`), and is maintained by [Gnani.ai](https://gnani.ai/).

<Note>
  The PyPI package is `gnani-vachana`, but the Python import package is `gnani`. Install `gnani-vachana`, then `from gnani.stt import ...`.
</Note>

***

## Installation

```bash theme={null}
pip install gnani-vachana
```

Or with [uv](https://docs.astral.sh/uv/):

```bash theme={null}
uv add gnani-vachana
```

**Requirements:** Python 3.9+

***

## Authentication

You need a Gnani API key — generate one on the [Gnani API platform](https://app.gnani.ai/voice). A single API key authenticates both STT and TTS; no `organization_id` or `user_id` is required.

The recommended approach is the `GNANI_API_KEY` environment variable, which every client reads automatically:

```bash theme={null}
export GNANI_API_KEY="your-api-key"
```

```python theme={null}
from gnani.stt import GnaniSTTClient

client = GnaniSTTClient()   # picks up GNANI_API_KEY
```

Or pass it explicitly:

```python theme={null}
client = GnaniSTTClient(api_key="your-api-key")
```

If neither is present, the constructor raises `AuthenticationError` immediately — before any network call.

<Note>
  If you are upgrading from an SDK version older than `0.7.x`, remove the `organization_id` and `user_id` constructor arguments. They are no longer accepted.
</Note>

***

## Choosing a client

Each API has one class per transport. Pick by latency requirement, not by preference — they return the same audio and the same transcripts.

### Speech-to-Text

| Class | Transport | Use it for |
| - | - | - |
| `GnaniSTTClient` | REST — `POST /stt/v3` | Pre-recorded files up to 60 s. Synchronous, one call, one transcript. |
| `GnaniSTTStreamClient` | WebSocket — `/stt/v3/stream` | Live microphone or telephony audio. Server-side VAD emits a transcript per speech segment. `async`. |
| `GnaniSTTBatchClient` | Batch jobs — `/stt/v3/batch/jobs` | Many or long recordings. Uploads, starts, waits, and fetches transcripts in one call. |
| `AsyncGnaniSTTBatchClient` | Batch jobs, `asyncio` | The same batch API for async code. |

### Text-to-Speech

| Class | Transport | Use it for |
| - | - | - |
| `GnaniTTSClient` | REST — `POST /api/v1/tts/inference` | Batch synthesis. Returns the complete audio in one response. |
| `GnaniTTSStreamClient` | SSE — `POST /api/v1/tts/sse` | Progressive playback with lower time-to-first-audio than REST. Synchronous generator. |
| `GnaniTTSRealtimeClient` | WebSocket — `/api/v1/tts` | Lowest latency, for conversational agents. `async`. |

<Tip>
  The two streaming STT/TTS clients are `async`; the REST and SSE clients are ordinary synchronous Python. You can mix them freely in the same program.
</Tip>

***

## Your first request

<Tabs>
  <Tab title="Speech-to-Text">
    ```python theme={null}
    from gnani.stt import GnaniSTTClient

    client = GnaniSTTClient()

    result = client.transcribe("recording.wav", language_code="hi-IN")
    print(result["transcript"])
    ```

    ```text theme={null}
    नमस्ते, आप कैसे हैं?
    ```

    Continue to [Speech-to-Text →](/python-sdk/speech-to-text)
  </Tab>

  <Tab title="Batch Speech-to-Text">
    ```python theme={null}
    from gnani.stt import GnaniSTTBatchClient

    client = GnaniSTTBatchClient()

    # 1. Create the job (uploads the files)
    job = client.create_job(
        ["call1.wav", "call2.wav"],
        language_code="hi-IN",
        start=False,          # create only; omit to start automatically
    )

    # 2. Start it
    job.start()

    # 3. Wait until it finishes
    job.wait()

    # 4. Read the transcripts
    for f in job.files():
        print(f.name, f.text if f.ok else f.error)

    job.save("./outputs")
    ```

    Continue to [Batch Speech-to-Text →](/python-sdk/speech-to-text-batch)
  </Tab>

  <Tab title="Text-to-Speech">
    ```python theme={null}
    from gnani.tts import GnaniTTSClient

    client = GnaniTTSClient()

    audio = client.synthesize(
        "नमस्ते, आप कैसे हैं?",
        voice="Nalini",
        model="timbre-v2.5",
        language="hi-IN",
        output_file="output.wav",
    )
    ```

    `output.wav` is written to disk, and the same bytes are returned so you can stream or upload them instead.

    Continue to [Text-to-Speech →](/python-sdk/text-to-speech)
  </Tab>
</Tabs>

<Warning>
  Always pass `model="timbre-v2.5"` on TTS calls. The SDK still defaults to `timbre-v2.0`, which the API no longer serves — omitting `model` returns `400` with `The supported models are "timbre-v2.5"`.
</Warning>

***

## Error handling

Each sub-package defines its own exception hierarchy, rooted at `GnaniSTTError` and `GnaniTTSError`. Catching the root class catches everything the SDK raises.

| Exception | Raised when |
| - | - |
| `AuthenticationError` | No API key was passed and `GNANI_API_KEY` is unset. |
| `APIError` | The API returned a non-200 response. Carries `.status_code` and `.body`. |
| `InvalidAudioError` | *(STT only)* The audio file is missing, or its extension is unsupported. |
| `StreamConnectionError` | The WebSocket connection could not be established. |
| `StreamClosedError` | An operation was attempted on a closed stream. |
| `StreamError` | The server sent an error event mid-stream. |

```python theme={null}
from gnani.stt import GnaniSTTClient
from gnani.stt.exceptions import APIError, GnaniSTTError, InvalidAudioError

client = GnaniSTTClient()

try:
    result = client.transcribe("recording.wav", language_code="hi-IN")
except InvalidAudioError as exc:
    print(f"Bad input: {exc}")
except APIError as exc:
    print(f"API returned {exc.status_code}: {exc.body}")
except GnaniSTTError as exc:
    print(f"SDK error: {exc}")
```

`ValueError` is raised — before any request leaves your process — for invalid parameter combinations such as an unknown voice, an unsupported sample rate, or `speed` outside `0.85`–`1.15`.

***

## Request IDs

Every method accepts an optional `request_id`. When omitted, the SDK generates one and sends it as `X-API-Request-ID`. It is echoed back in STT REST responses and in TTS WebSocket events.

```python theme={null}
result = client.transcribe(
    "recording.wav",
    language_code="hi-IN",
    request_id="order-4471-attempt-1",
)
```

Log it. It is the fastest way for Gnani support to trace a single call end to end.

***

## Pointing at a different environment

All clients take `base_url`, defaulting to `https://api.vachana.ai`. The streaming clients derive their WebSocket URL from it automatically (`https` → `wss`).

```python theme={null}
client = GnaniSTTClient(base_url="https://api.vachana.ai")
```

***

## Further Reading

<CardGroup cols={2}>
  <Card title="Speech-to-Text" icon="microphone" href="/python-sdk/speech-to-text">
    REST transcription and realtime streaming with the Python SDK.
  </Card>

  <Card title="Text-to-Speech" icon="waveform" href="/python-sdk/text-to-speech">
    REST, SSE, and WebSocket synthesis with the Python SDK.
  </Card>
</CardGroup>

* [`gnani-vachana` on PyPI](https://pypi.org/project/gnani-vachana/) — releases and changelog
* [STT REST API](/api/STT/speech-to-text) · [STT Realtime API](/api/STT/stt-websocket) — underlying HTTP reference
* [TTS REST](/api/TTS/tts-inference) · [TTS SSE](/api/TTS/tts-sse) · [TTS Realtime](/api/TTS/tts-websocket) — underlying HTTP reference
* [LiveKit Plugin](/livekit/introduction) · [Pipecat Plugin](/pipecat/introduction) — framework integrations built on these same APIs


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.