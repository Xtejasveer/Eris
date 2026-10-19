> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Python SDK — Speech-to-Text

> Transcribe files with the REST client and live audio with the realtime WebSocket client.

## Overview

The SDK exposes two STT clients for single recordings and live audio, plus a [batch client](/python-sdk/speech-to-text-batch) for many or long files. All authenticate with a single API key and support the same ten Indian languages.

| Class | Transport | Audio source | Returns |
| - | - | - | - |
| `GnaniSTTClient` | REST — `POST /stt/v3` | A file or `bytes`, up to 60 s | One transcript, synchronously |
| `GnaniSTTStreamClient` | WebSocket — `/stt/v3/stream` | A live PCM stream | A transcript per speech segment, as they are detected |
| `GnaniSTTBatchClient` | Batch jobs — `/stt/v3/batch/jobs` | Many or long files | Transcripts when the job finishes — see [Batch STT](/python-sdk/speech-to-text-batch) |

```python theme={null}
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient
```

***

## REST — transcribe a file

Pass a path, a `Path`, or any binary file object. Paths are opened and closed for you.

```python theme={null}
from gnani.stt import GnaniSTTClient

client = GnaniSTTClient()   # or GnaniSTTClient(api_key="your-api-key")

result = client.transcribe("recording.wav", language_code="hi-IN")

print(result["transcript"])
print(result["request_id"])
```

### Response

`transcribe()` returns the parsed JSON body as a `dict`:

```json theme={null}
{
  "success": true,
  "request_id": "019fd17d-1106-7265-88ab-3ed12d029292",
  "timestamp": "20260917_143052.123",
  "transcript": "नमस्ते, आप कैसे हैं?"
}
```

### Parameters

| Parameter | Type | Default | Description |
| - | - | - | - |
| `audio` | `str \| Path \| BinaryIO` | *required* | Path to an audio file, or an open binary file object. |
| `language_code` | `str` | `"en-IN"` | BCP-47 code. See [Supported languages](#supported-languages). |
| `format` | `str` | `"verbatim"` | `"verbatim"` for spoken-form output, `"transcribe"` to enable ITN. |
| `itn_native_numerals` | `bool` | `False` | With `format="transcribe"`, render digits in the native script. |
| `request_id` | `str` | auto | Custom ID for tracing. |

Accepted file extensions: `.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac`. Anything else raises `InvalidAudioError` locally, without a network round trip.

### Inverse Text Normalization

`format="transcribe"` rewrites numbers, currency, dates, and phone numbers into conventional written form. Add `itn_native_numerals=True` to keep digits in the target script.

<CodeGroup>
  ```python Verbatim theme={null}
  result = client.transcribe("invoice.wav", language_code="hi-IN")
  # "पाँच हज़ार रुपये"
  ```

  ```python ITN theme={null}
  result = client.transcribe(
      "invoice.wav",
      language_code="hi-IN",
      format="transcribe",
  )
  # "₹5,000"
  ```

  ```python ITN + native numerals theme={null}
  result = client.transcribe(
      "invoice.wav",
      language_code="hi-IN",
      format="transcribe",
      itn_native_numerals=True,
  )
  # "₹५,०००"
  ```
</CodeGroup>

<Note>
  ITN is currently supported for `hi-IN` and `en-IN` only. See [ITN reference](/api/STT/speech-to-text#inverse-text-normalization-itn).
</Note>

***

## REST — transcribe raw bytes

When audio never touches disk — an upload handler, an S3 object, a recording buffer — use `transcribe_bytes()`. The `filename` is a format hint for the server, not a real path.

```python theme={null}
audio_bytes = request.files["audio"].read()

result = client.transcribe_bytes(
    audio_bytes,
    filename="upload.wav",
    language_code="en-IN",
)
print(result["transcript"])
```

### Parameters

| Parameter | Type | Default | Description |
| - | - | - | - |
| `audio_bytes` | `bytes` | *required* | Raw audio content. |
| `filename` | `str` | `"audio.wav"` | Extension tells the server which decoder to use. |
| `language_code` | `str` | `"en-IN"` | BCP-47 code. |
| `format` | `str` | `"verbatim"` | `"verbatim"` or `"transcribe"`. |
| `itn_native_numerals` | `bool` | `False` | Native-script digits when ITN is on. |
| `request_id` | `str` | auto | Custom ID for tracing. |

***

## Realtime — streaming WebSocket

`GnaniSTTStreamClient` streams raw PCM to the server. Server-side VAD detects end of speech and emits a transcript per segment — you do not need to decide where utterances end.

The client is `async` and works as an async context manager: entering connects, exiting closes.

```python theme={null}
import asyncio

from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent


async def main():
    async with GnaniSTTStreamClient(language_code="hi-IN", sample_rate=16000) as stream:
        with open("audio.pcm", "rb") as f:
            while chunk := f.read(1024):
                await stream.send_audio(chunk)
                await asyncio.sleep(0.032)     # real-time pacing, 32 ms per frame

        async for event in stream:
            if isinstance(event, StreamTranscriptEvent):
                print(event.text)


asyncio.run(main())
```

### Constructor parameters

| Parameter | Type | Default | Description |
| - | - | - | - |
| `api_key` | `str` | `GNANI_API_KEY` | Your API key. |
| `language_code` | `str` | `"en-IN"` | BCP-47 code. Streaming is **single-language** — one locale per session. |
| `sample_rate` | `int` | `16000` | `8000`, `16000`, `44100`, or `48000`. |
| `format` | `str` | `"verbatim"` | `"verbatim"` or `"transcribe"`. |
| `itn_native_numerals` | `bool` | `False` | Native-script digits when ITN is on. |
| `base_url` | `str` | `"https://api.vachana.ai"` | Converted to `wss://` automatically. |

Invalid values raise `ValueError` in the constructor, before connecting.

### PCM specification

Audio must be **raw PCM binary frames** — no WAV, MP3, or other container mid-stream.

| Property | 16 kHz | 8 kHz |
| - | - | - |
| Encoding | PCM signed 16-bit little-endian | PCM signed 16-bit little-endian |
| Channels | 1 (mono) | 1 (mono) |
| Samples per frame | 512 | 512 |
| **Bytes per frame** | **1,024** | **1,024** |
| Frame duration | 32 ms | 64 ms |

The SDK exports these as constants so you never hard-code them:

```python theme={null}
from gnani.stt import STREAM_CHUNK_BYTES, STREAM_CHUNK_SAMPLES

STREAM_CHUNK_SAMPLES   # 512
STREAM_CHUNK_BYTES     # 1024
```

<Warning>
  Send frames at real-time cadence. Flushing a whole file as fast as the socket accepts it starves the VAD of timing information and degrades segmentation. `asyncio.sleep(bytes / 2 / sample_rate)` is the correct pause between frames — or use `stream_audio()` below, which paces for you.
</Warning>

***

## Realtime — three usage patterns

<Tabs>
  <Tab title="Callbacks (simplest)">
    `stream_audio()` sends and receives concurrently, paces frames for you, and returns every transcript when the source is exhausted. Best for transcribing a file or a finite stream.

    ```python theme={null}
    import asyncio

    from gnani.stt import GnaniSTTStreamClient


    async def main():
        async with GnaniSTTStreamClient(language_code="hi-IN") as stream:
            with open("audio.pcm", "rb") as f:
                transcripts = await stream.stream_audio(
                    f,
                    on_transcript=lambda e: print(f"[{e.segment_index}] {e.text}"),
                    on_error=lambda e: print(f"error: {e.message}"),
                )

        full_text = " ".join(t.text for t in transcripts)
        print(full_text)


    asyncio.run(main())
    ```

    | Parameter | Type | Default | Description |
    | - | - | - | - |
    | `audio_source` | `AsyncIterator[bytes] \| BinaryIO` | *required* | Async iterator of chunks, or a binary file object. |
    | `on_transcript` | `callable` | `None` | Called per `StreamTranscriptEvent`. |
    | `on_processing` | `callable` | `None` | Called per `StreamProcessingEvent`. |
    | `on_error` | `callable` | `None` | Called per `StreamErrorEvent`. If unset, a `StreamError` is raised instead. |
    | `chunk_size` | `int` | `1024` | Bytes per frame. |
    | `realtime_pace` | `bool` | `True` | Sleep between frames to match real time. |
  </Tab>

  <Tab title="Async iteration">
    Iterate the client directly to handle every event type as it arrives. Best for live microphone or telephony audio, where sending never ends.

    ```python theme={null}
    import asyncio

    from gnani.stt import (
        GnaniSTTStreamClient,
        StreamConnectedEvent,
        StreamErrorEvent,
        StreamProcessingEvent,
        StreamTranscriptEvent,
    )


    async def consume(stream):
        async for event in stream:
            if isinstance(event, StreamConnectedEvent):
                print(f"connected at {event.sample_rate} Hz")
            elif isinstance(event, StreamProcessingEvent):
                print("end of speech — transcribing…")
            elif isinstance(event, StreamTranscriptEvent):
                print(f"{event.text}  ({event.latency} ms)")
            elif isinstance(event, StreamErrorEvent):
                print(f"error: {event.message}")


    async def main():
        async with GnaniSTTStreamClient(language_code="en-IN") as stream:
            consumer = asyncio.create_task(consume(stream))

            async for chunk in microphone_frames():        # your audio source
                await stream.send_audio(chunk)

            await stream.close()
            await consumer


    asyncio.run(main())
    ```

    Run sending and receiving as separate tasks. Awaiting them in sequence on an unbounded source means transcripts are never read.
  </Tab>

  <Tab title="Manual lifecycle">
    Call `connect()` and `close()` yourself when the connection outlives a single block — for example, a stream owned by a long-lived agent object.

    ```python theme={null}
    stream = GnaniSTTStreamClient(language_code="ta-IN", sample_rate=8000)

    connected = await stream.connect()
    print(connected.sample_rate, connected.chunk_size)

    await stream.send_audio(frame)          # repeat per 1,024-byte frame

    transcripts = await stream.close()      # returns every transcript from the session
    ```

    | Member | Description |
    | - | - |
    | `await connect(request_id=None)` | Opens the socket, returns the `StreamConnectedEvent`. |
    | `await send_audio(chunk)` | Sends one binary frame. Raises `StreamClosedError` if not connected. |
    | `await close()` | Closes gracefully, returns `list[StreamTranscriptEvent]`. |
    | `is_connected` | `bool` — whether the socket is open. |
    | `connected_config` | The `StreamConnectedEvent`, or `None` before connecting. |
    | `transcripts` | Every transcript received so far this session. |
  </Tab>
</Tabs>

***

## Stream events

Every event is a typed dataclass. Each carries `.raw`, the untouched JSON payload, for anything not surfaced as an attribute.

<ResponseField name="StreamConnectedEvent" type="dataclass">
  Received once, immediately after the handshake.

  <Expandable title="Attributes">
    <ResponseField name="message" type="str">Human-readable status from the server.</ResponseField>
    <ResponseField name="timestamp" type="str">ISO-8601 timestamp.</ResponseField>
    <ResponseField name="sample_rate" type="int">Negotiated sample rate in Hz.</ResponseField>
    <ResponseField name="chunk_size" type="int">Expected frame size in samples.</ResponseField>
  </Expandable>
</ResponseField>

<ResponseField name="StreamProcessingEvent" type="dataclass">
  VAD has detected end of speech and transcription has begun. Useful for a "thinking" indicator.

  <Expandable title="Attributes">
    <ResponseField name="timestamp" type="str">ISO-8601 timestamp.</ResponseField>
  </Expandable>
</ResponseField>

<ResponseField name="StreamTranscriptEvent" type="dataclass">
  The transcript for one completed speech segment.

  <Expandable title="Attributes">
    <ResponseField name="text" type="str">The transcribed text.</ResponseField>
    <ResponseField name="audio_duration_ms" type="int">Duration of the segment in milliseconds.</ResponseField>
    <ResponseField name="segment_id" type="str">Unique identifier for the segment.</ResponseField>
    <ResponseField name="segment_index" type="str">Ordinal index within the session.</ResponseField>
    <ResponseField name="latency" type="int">Server-side processing latency in milliseconds.</ResponseField>
    <ResponseField name="timestamp" type="str">ISO-8601 timestamp.</ResponseField>
  </Expandable>
</ResponseField>

<ResponseField name="StreamErrorEvent" type="dataclass">
  The server encountered an error. The connection may still be usable.

  <Expandable title="Attributes">
    <ResponseField name="message" type="str">Error description.</ResponseField>
    <ResponseField name="timestamp" type="str">ISO-8601 timestamp.</ResponseField>
  </Expandable>
</ResponseField>

***

## Supported languages

Both clients support the same ten languages. STT uses the `-IN` suffix throughout.

| Code | Language | Code | Language |
| - | - | - | - |
| `en-IN` | English (India) | `mr-IN` | Marathi |
| `hi-IN` | Hindi | `bn-IN` | Bengali |
| `gu-IN` | Gujarati | `ml-IN` | Malayalam |
| `ta-IN` | Tamil | `pa-IN` | Punjabi |
| `kn-IN` | Kannada | `te-IN` | Telugu |

Read them at runtime instead of hard-coding:

```python theme={null}
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient

GnaniSTTClient.supported_languages()         # REST
GnaniSTTStreamClient.supported_languages()   # realtime
# {"en-IN": "English (India)", "hi-IN": "Hindi", ...}
```

<Note>
  Realtime streaming is single-language — one `language_code` per session. Multi-language input is supported only on REST `POST /stt/v3` via `multi_lang_codes`, which is not yet exposed through the SDK.
</Note>

***

## Error handling

```python theme={null}
from gnani.stt import GnaniSTTStreamClient
from gnani.stt.exceptions import (
    APIError,
    AuthenticationError,
    InvalidAudioError,
    StreamClosedError,
    StreamConnectionError,
    StreamError,
)
```

| Exception | Raised when |
| - | - |
| `AuthenticationError` | No API key passed and `GNANI_API_KEY` unset. |
| `InvalidAudioError` | File missing, or extension unsupported. |
| `APIError` | Non-200 REST response. Carries `.status_code` and `.body`. |
| `StreamConnectionError` | The WebSocket handshake failed. |
| `StreamClosedError` | `send_audio()` called on a closed stream. |
| `StreamError` | The server sent an error event and no `on_error` callback was provided. |

All six inherit from `GnaniSTTError`.

***

## Further Reading

* [Python SDK overview](/python-sdk/introduction) — installation, auth, client selection
* [Python SDK — Text-to-Speech](/python-sdk/text-to-speech)
* [STT REST API](/api/STT/speech-to-text) — endpoint reference
* [STT Realtime API](/api/STT/stt-websocket) — WebSocket protocol reference


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.