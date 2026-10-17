> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Python SDK — Batch Speech-to-Text

> Transcribe many or long recordings asynchronously with one call: upload, start, wait, and fetch transcripts.

## Overview

`GnaniSTTBatchClient` wraps the whole [Batch STT API](/api/STTBatch/Introduction) — create a job, start it, poll until it finishes, then download each transcript — so you do not hand-roll multipart uploads, polling loops, or presigned-URL downloads.

| Class | Style | Use it for |
| - | - | - |
| `GnaniSTTBatchClient` | Synchronous | Scripts, notebooks, cron jobs, and worker processes. |
| `AsyncGnaniSTTBatchClient` | `asyncio` | Web servers and async pipelines. Same methods, awaited. |

```python theme={null}
from gnani.stt import GnaniSTTBatchClient, AsyncGnaniSTTBatchClient
```

<Note>
  Batch support needs `gnani-vachana` **0.8.1 or later**. Earlier 0.8.0 does not retry rate-limited requests, so `transcribe()` can fail right after submitting a job.

  ```bash theme={null}
  pip install -U "gnani-vachana>=0.8.1"
  ```
</Note>

For short clips (under about 60 seconds) use [REST](/python-sdk/speech-to-text#rest--transcribe-a-file). For live audio use the [realtime client](/python-sdk/speech-to-text#realtime--streaming-websocket).

***

## Quick start

```python theme={null}
from gnani.stt import GnaniSTTBatchClient

client = GnaniSTTBatchClient()   # reads GNANI_API_KEY

result = client.transcribe(["call1.wav", "call2.wav"], language_code="hi-IN")

print(result[0].text)
result.save("./outputs")         # one JSON file per transcript
```

`transcribe()` creates the job, starts it, waits for it to finish, and returns the files with their transcripts. A progress bar is shown if [`tqdm`](https://pypi.org/project/tqdm/) is installed; otherwise a log line is printed each time progress changes.

```text theme={null}
INFO  gnani | [STT Batch] job created | job_id=7baf66ba-de2a-4943-961e-35afe08f797b
INFO  gnani | [STT Batch] 7baf66ba-de2a-4943-961e-35afe08f797b COMPLETED 100%
```

```python theme={null}
for f in result:
    print(f.name, f.status, f.duration)   # call1.wav COMPLETED 8.22
    if f.ok:
        print(f.text)
    else:
        print("failed:", f.error)
```

***

## What you can pass as `files`

`files` accepts any of these, alone or in a list. Local files and URLs cannot be mixed in one job.

| You pass | Example |
| - | - |
| A file path | `"call.wav"` or `Path("call.wav")` |
| A directory | `"./recordings/"` — searched recursively for supported audio and ZIPs |
| A glob pattern | `"./recordings/2026-*/*.wav"` |
| A ZIP archive | `"batch.zip"` — extracted server-side |
| Raw bytes | `("call.wav", audio_bytes)` — a `(name, bytes)` tuple. A bare `bytes` object is sent as `audio_0.wav`. |
| An open binary file | `open("call.wav", "rb")` |
| Public HTTPS URLs | `["https://cdn.example.com/a.mp3", "https://cdn.example.com/b.mp3"]` |

The SDK checks your input before uploading anything, so a mistake fails in milliseconds instead of after a long upload:

| Check | Limit |
| - | - |
| Files per job | 100 |
| Size per audio file | 10 MB |
| ZIP size | 50 MB compressed |
| Formats | `.wav` `.mp3` `.mp4` `.flac` `.ogg` `.opus` `.m4a` `.aac` `.webm` `.amr`, or a `.zip` |

<Tip>
  Only the file's base name is sent to the server, never its path. This matters: a multipart filename containing `../` is blocked at the network edge with a `403` HTML page that never reaches Gnani's logs. With the SDK, `open("../audio/call.wav")` is safe.
</Tip>

<Warning>
  Files larger than 10 MB are not supported by the SDK yet. Split long recordings, or pass public URLs.
</Warning>

***

## Options

`transcribe()` takes `files` and `language_code`, plus every option below. `create_job()` takes the same options.

```python theme={null}
result = client.transcribe(
    "./recordings/",
    language_code="hi-IN,en-IN",
    speakers=2,
    denoise=True,
    bias_words=["HDFC", "Prisma", "EMI"],
)
```

| Parameter | Type | Default | API field | Description |
| - | - | - | - | - |
| `files` | see above | *required* | — | The audio to transcribe. |
| `language_code` | `str` | `"en-IN"` | `language_code` | One code (`"hi-IN"`), several comma-separated (`"hi-IN,en-IN"`), or `"auto"`. See [Language identification](/api/STTBatch/Introduction#language-identification). The first code is the fallback. |
| `model` | `str` | `"gnani-prisma-v2.5"` | `model` | Transcription model. |
| `diarization` | `bool` | `False` | `with_diarization` | Label who spoke each segment. |
| `speakers` | `int` | `None` | `num_speakers` | Most speakers to separate, 1–8. A ceiling, not a target. Setting it turns diarization on. |
| `multi_channel` | `bool` | `False` | `is_multi_channel` | Set only for true multi-channel audio. |
| `denoise` | `bool` | `False` | `with_denoise` | Clean noisy recordings first. Slower; leave off for clean audio. |
| `bias_words` | `list[str] \| str` | `None` | `bias_list` | Up to 100 words to favour, such as brand names. A comma-separated string also works. |
| `bias_score` | `float` | `None` | `bias_score` | Boost strength: `0.0`, `0.5`, `1.0`, `1.5`, or `2.0`. Defaults to `1.0` when `bias_words` is set. |
| `callback_url` | `str` | `None` | `callback_url` | HTTPS webhook called when the job reaches a terminal state. See [Webhooks](#webhooks). |
| `start` | `bool` | `True` | — | `create_job()` only. Set `False` to create without starting. |
| `timeout` | `float` | `None` | — | `transcribe()` only. Seconds to wait for the job to finish. |
| `progress` | `bool` | `True` | — | `transcribe()` only. Show progress while waiting. |
| `raise_on_failure` | `bool` | `True` | — | `transcribe()` only. See [Handling failures](#handling-failures). |

The SDK raises `ValueError` before any network call for an unsupported language code, `speakers` outside 1–8, a `bias_score` that is not one of the listed values, or more than 100 `bias_words`.

***

## Step by step

Use `create_job()` when a job is long-running, when you want to keep its ID, or when another process will collect the results.

```python theme={null}
from gnani.stt import GnaniSTTBatchClient

client = GnaniSTTBatchClient()

job = client.create_job("./recordings/", language_code="hi-IN")   # starts automatically
print(job.id)                                  # save this to resume later

job.wait(timeout=3600, on_progress=lambda j: print(j.status, j.percent))

for f in job.files():
    print(f.name, f.text if f.ok else f.error)

job.save("./outputs", text_files=True)         # writes .json and .txt per file
```

### Resume a job later

A job keeps running on Gnani's servers whether or not your program is. Re-attach with its ID:

```python theme={null}
job = client.get_job("7baf66ba-de2a-4943-961e-35afe08f797b")
print(job.status, job.percent)

job.wait()
job.save("./outputs")
```

### Create now, start later

```python theme={null}
job = client.create_job("call.wav", language_code="en-IN", start=False)
print(job.status)    # CREATED

job.start()
print(job.status)    # STARTING
```

### List and cancel jobs

`list_jobs()` follows pagination for you.

```python theme={null}
for job in client.list_jobs(status="COMPLETED", limit=20):
    print(job.id, job.status, job.completed_files, "/", job.total_files)

client.get_job("<job_id>").cancel(reason="uploaded the wrong files")
```

***

## Results

### `BatchJob`

| Member | Description |
| - | - |
| `id` | The job ID. |
| `status` | `CREATED`, `STARTING`, `QUEUED`, `IN_PROGRESS`, `COMPLETED`, `PARTIAL_FAILURE`, `FAILED`, `START_FAILED`, `CANCELLING`, or `CANCELLED`. See [Job statuses](/api/STTBatch/Introduction#job-statuses). |
| `percent` | Overall progress, 0–100. Reaches 100 only when the job is finished. |
| `total_files`, `completed_files`, `failed_files` | File counters, once the job has been read. |
| `cancel_reason` | Why the job was cancelled or could not start. |
| `is_done` | `True` once the status is terminal. |
| `refresh()` | Re-read status and progress. |
| `start()` | Start a job created with `start=False`. |
| `wait(...)` | Block until the job finishes. See [Waiting](#waiting-for-a-job). |
| `files(status=None)` | All files in the job, across pages. Pass `status="COMPLETED"` to filter. |
| `save(directory, text_files=False)` | Write each completed transcript to `directory` and return the paths. |
| `cancel(reason=None)` | Cancel the job. |

### `BatchFile`

| Member | Description |
| - | - |
| `name` | The file name you uploaded. |
| `status` | `COMPLETED`, `FAILED`, `SKIPPED`, and so on. |
| `ok` | `True` when the file is `COMPLETED`. |
| `duration` | Audio length in seconds. |
| `error` | Why a file failed, for example `Empty transcript after 3 retries`. |
| `progress_percent`, `stage` | How far this file has got, and what it is doing. |
| `text` | The full transcript as one string. |
| `segments` | A list of `BatchSegment` with `start`, `end`, `text`, and `speaker`. |
| `transcript` | The raw transcript document as a `dict`. |

`text`, `segments`, and `transcript` download the transcript the first time you read them. Transcript links expire after one hour; if one has expired the SDK fetches a fresh link and retries once, so you never handle that yourself. Reading them on a file that is not `COMPLETED` raises `ValueError` with the file's status and error.

```python theme={null}
for f in result:
    if f.ok:
        for seg in f.segments:
            print(f"[{seg.start:6.1f}–{seg.end:6.1f}] speaker {seg.speaker}: {seg.text}")
```

```text theme={null}
[   0.2–   3.0] speaker 1: hello yes i can hear you
[   3.4–   7.1] speaker 1: i am calling about my electricity bill for this month
```

### `BatchResult`

What `transcribe()` returns. Iterate it, index it, or use:

| Member | Description |
| - | - |
| `job` | The finished `BatchJob`. |
| `files` | The list of `BatchFile`. `result[0]` and `for f in result` also work. |
| `failed` | The files that are not `COMPLETED`. |
| `text` | Every successful transcript joined, one file per paragraph. |
| `save(directory, text_files=False)` | Write transcripts to disk. |

`save()` names each file after its audio (`call1.wav` becomes `call1.json`). Two files with the same name get `_2`, `_3`, and so on. Failed files are skipped.

***

## Waiting for a job

`wait()` polls the job until it reaches a terminal status.

```python theme={null}
job.wait(
    timeout=3600,                 # seconds; None waits forever
    poll_interval=10,             # seconds between polls
    progress=True,
    on_progress=lambda j: print(j.status, j.percent),
)
```

| Parameter | Default | Description |
| - | - | - |
| `timeout` | `None` | Seconds to wait before raising `BatchTimeoutError`. The job keeps running. |
| `poll_interval` | `10` | Seconds between polls. Never goes below 10, the documented minimum. |
| `max_poll_interval` | `30` | The interval grows gradually up to this on long jobs. |
| `progress` | `False` | Show a progress bar (with `tqdm`) or log lines. |
| `on_progress` | `None` | Callback called with the job after each poll. |
| `raise_on_failure` | `True` | See below. |

Pressing Ctrl-C while waiting stops your program but **not** the job. The job ID is logged so you can resume with `get_job()`.

***

## Handling failures

A job that finishes is not always a job that succeeded. `wait()` and `transcribe()` treat the final status like this:

| Final status | What happens |
| - | - |
| `COMPLETED` | Returns normally. |
| `PARTIAL_FAILURE` | Returns normally. Some files worked; check each file's `ok` and `error`. |
| `FAILED`, `START_FAILED`, `CANCELLED` | Raises `BatchJobFailedError` with `job_id`, `status`, and `reason`. |
| Timed out | Raises `BatchTimeoutError` with `job_id` and `timeout`. The job is still running. |

```python theme={null}
from gnani.stt import BatchJobFailedError, BatchTimeoutError

try:
    result = client.transcribe("./recordings/", language_code="hi-IN", timeout=1800)
except BatchTimeoutError as e:
    print("still running, resume with", e.job_id)
except BatchJobFailedError as e:
    print(e.status, e.reason)
else:
    for f in result.failed:
        print(f.name, "failed:", f.error)
```

Pass `raise_on_failure=False` to get the job back for any final status instead of an exception.

### Other errors

| Error | When |
| - | - |
| `AuthenticationError` | No API key passed and `GNANI_API_KEY` is not set. |
| `InvalidAudioError` | A file is missing, an unsupported format, over 10 MB, over the 100-file limit, or no files were given. |
| `ValueError` | An invalid option, such as an unsupported `language_code`. |
| `APIError` | The API returned an error. `status_code` and `body` (the raw response) are available. |

```python theme={null}
from gnani.stt import APIError

try:
    client.get_job("01900000-0000-7000-8000-000000000000")
except APIError as e:
    print(e.status_code, e.body)
    # 404 {"error": "JOB_NOT_FOUND", "message": "Job 01900000-... not found"}
```

### Rate limits

The API limits how fast one key can make requests. Rate-limited requests (`429`) are retried automatically, up to 5 times, waiting for the server's `Retry-After` if it sends one and otherwise 1, 2, 4, 8, then 16 seconds. Status and file reads are also retried on `502`, `503`, and `504`. If every retry is refused, `APIError` is raised.

***

## Async

`AsyncGnaniSTTBatchClient` has the same methods and options. Calls run on worker threads, so they never block your event loop and no extra dependency is needed.

```python theme={null}
import asyncio
from gnani.stt import AsyncGnaniSTTBatchClient


async def main():
    client = AsyncGnaniSTTBatchClient()

    result = await client.transcribe("./recordings/", language_code="hi-IN")
    print(result[0].text)
    await result.save("./outputs")

    async for job in client.list_jobs(status="COMPLETED"):
        print(job.id)


asyncio.run(main())
```

Differences from the sync client:

| Sync | Async |
| - | - |
| `client.transcribe(...)` | `await client.transcribe(...)` |
| `job.wait()`, `job.refresh()`, `job.start()`, `job.cancel()` | `await` each of them |
| `job.files()` | `await job.files()` |
| `job.save(dir)` and `result.save(dir)` | `await` each of them |
| `for job in client.list_jobs()` | `async for job in client.list_jobs()` |
| `f.text` downloads on first read | Transcripts are downloaded for you by `transcribe()`. After `job.files()`, call `await f.load()` or use `await job.files(load=True)` first. Reading `f.text` before then raises `RuntimeError`. |

`transcribe()` downloads transcripts for up to eight files at a time, so a 100-file job finishes quickly. Cancelling the task that is awaiting `wait()` leaves the job running on the server.

```python theme={null}
job = await client.get_job("<job_id>")
await job.wait()

for f in await job.files(load=True):    # loads every transcript concurrently
    print(f.name, f.text if f.ok else f.error)
```

***

## Webhooks

Pass `callback_url` to be notified when the job reaches a terminal state, instead of (or as well as) waiting:

```python theme={null}
job = client.create_job(
    "./recordings/",
    language_code="hi-IN",
    callback_url="https://example.com/hooks/stt",
)
print(job.id)    # no need to wait
```

Webhooks are best-effort — see [Webhooks](/api/STTBatch/Introduction#webhooks) for the payload and events. Polling with `wait()` or `get_job()` remains the source of truth.

***

## Supported languages

Batch supports the same ten languages as the REST client:

```python theme={null}
GnaniSTTBatchClient.supported_languages()
```

`en-IN`, `hi-IN`, `bn-IN`, `gu-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `pa-IN`, `ta-IN`, `te-IN`. Pass `"auto"` to identify the language among all of them, or a comma-separated list to restrict identification to the languages you expect.

***

## Related

<CardGroup cols={2}>
  <Card title="Batch STT API" icon="layer-group" href="/api/STTBatch/Introduction">
    The HTTP endpoints, statuses, limits, and webhook payloads behind the SDK.
  </Card>

  <Card title="REST and realtime STT" icon="microphone" href="/python-sdk/speech-to-text">
    Short clips and live audio with the same package.
  </Card>
</CardGroup>


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.