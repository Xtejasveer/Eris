# Eris

**An AI substitute teacher that teaches a class from the teacher's own material, in the teacher's own style.**

[![Live Demo](https://img.shields.io/badge/Live_Demo-Eris-1b6e66?style=flat-square)](https://eris.indiasouthcentral.cloudapp.azure.com/#/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

**Live demo:** [eris.indiasouthcentral.cloudapp.azure.com](https://eris.indiasouthcentral.cloudapp.azure.com/#/)

---

## Overview

When a teacher is away, the class usually gets a free period, a worksheet, or a substitute reading from the textbook. Eris lets the teacher keep teaching.

The teacher uploads their slides, notes, textbook pages or lab sheets and describes how they teach. Eris writes a lecture script in that voice. The teacher reviews it, edits anything, and approves it. Students then join with a class code and take the lesson on their own devices. A voiced tutor teaches across slides, a notebook, a code editor and interactive graphs, and answers students' doubts as they come up.

## How it works

1. **Upload.** The teacher adds PPTX, PDF, DOCX, TXT or Markdown files and a short teaching persona (tone, language, voice).
2. **Index.** Eris extracts text, slides, figures and book pages, describes images with a vision model, and builds a searchable index.
3. **Generate.** A planner sizes each part of the topic from the material itself. A writer produces the lesson in the teacher's voice, and a stager places every board action (slides, highlights, notes, graphs, code).
4. **Check.** Automated checks dry-run the code, verify the formulas and book answers, and confirm every key point is covered.
5. **Approve.** The teacher reviews the script in Studio, edits any line, and approves it. Nothing reaches students before approval.
6. **Teach.** A deterministic player runs the approved script. Speech and board actions stay in sync, and students can pause to ask a doubt by voice or text.

## Features

- **Teacher in the loop.** Every script is a draft until the teacher approves it. Any section can be edited or regenerated.
- **Length from the material.** There is no fixed duration. Eris goes deeper where the topic needs it and keeps simple parts brief.
- **Textbook teaching.** Eris opens the actual book page, highlights and underlines it, and works through book examples with the answer hidden until the class has solved them.
- **Four classroom boards.** Slides, a handwritten notebook, a code editor with a sandboxed terminal, and a visual board with flow diagrams and interactive graphs.
- **Live doubts.** Students ask by voice or text at any point. A LangGraph agent reads the current board and the course material, then answers with speech, notes, code or a graph. Guardrails screen both the question and the answer.
- **Ten Indian languages.** English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati and Punjabi, voiced with Gnani Timbre TTS.
- **Video tutor.** A talking video tutor in sync with the narration, with a browser-based 3D avatar as a lightweight fallback.
- **Courses and attendance.** Courses, chapters, prerequisite lessons and shared study material. Attendance records which parts of the lesson each student actually heard.

## Classroom boards

| Board | What it shows | Used when |
|---|---|---|
| Slides | The teacher's deck, with highlights and circles drawn on it | A PPTX or PDF deck is uploaded |
| Book | Textbook pages with highlights, underlines and worked examples | A textbook PDF is uploaded |
| Notebook | Handwritten notes, titles and highlights | Every lesson |
| Code | An editor and a sandboxed terminal that runs the program | The material contains code |
| Visual | Step-by-step flow diagrams and graphs with sliders | The topic has a process or a chart |

---

## Getting started

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An [OpenRouter](https://openrouter.ai) API key for a model that supports tool calling
- Optional: a Gnani API key for voice, LibreOffice for rendering PPTX slides as images, and Docker for the code sandbox

### Installation

```bash
git clone https://github.com/Xtejasveer/Eris.git
cd Eris

uv venv --python 3.12
source .venv/bin/activate        # Windows: .venv\Scripts\activate

uv pip install -r requirements.txt
uv pip install -r requirements-extras.txt   # optional: video tutor and local speech recognition

cp .env.example .env
```

### Configuration

Set at least these values in `.env`:

```ini
OPENROUTER_API_KEY=your_openrouter_key
LLM_MODEL=openai/gpt-4o-mini
GNANI_API_KEY=your_gnani_key      # optional; without it the browser's speech synthesis is used
```

Other useful settings:

| Variable | Purpose | Default |
|---|---|---|
| `TTS_VOICE`, `TTS_LANGUAGE`, `TTS_SPEED` | Classroom voice | `Kaveri`, `en-IN`, `0.85` |
| `JUDGE_ENABLED` | Run quality checks on generated scripts | `true` |
| `GUARDRAILS_ENABLED` | Screen students' questions and the answers | `true` |
| `VISION_ENABLED` | Describe pictures in the material at index time | `true` |
| `ERIS_SANDBOX` | Where programs run: `auto`, `docker`, `os` or `off` | `auto` |
| `ERIS_DEMO_LOGINS` | Show the demo accounts on the sign-in page | `true` |
| `ERIS_DEMO_CAN_GENERATE` | Allow demo accounts to generate scripts | `true` |
| `ERIS_TEACHER_SIGNUP` | Allow anyone to create a teacher account | `false` |

See [.env.example](.env.example) for the full list.

### Run

```bash
python main.py seed     # optional: demo accounts, courses and approved lessons
python main.py serve
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

- **Teachers** create courses, upload material, generate and review scripts, and share approved lessons.
- **Students** join with a class code, attend lessons and ask doubts.

The seed adds five ready-to-use demo lessons: Physics (projectile motion), History (French society), Mathematics (quadratic factorisation), Chemistry (carbonyl compounds) and Python (while loops).

---

## Deployment

The Docker setup runs Eris behind Caddy with automatic HTTPS:

```bash
docker compose up -d --build
```

See [deploy/README.md](deploy/README.md) and [deploy/azure.md](deploy/azure.md) for server setup and custom domains.

## Command-line interface

| Command | Description |
|---|---|
| `python main.py serve` | Start the web application |
| `python main.py seed` | Add the demo accounts, courses and lessons |
| `python main.py demo-snapshot` | Save the demo lessons' approved scripts into `templates/demo/` |
| `python main.py index --lecture <id>` | Build the knowledge base from `data/<id>/` |
| `python main.py generate --lecture <id>` | Write a draft script |
| `python main.py stage --lecture <id>` | Re-stage the saved lesson and report the result |
| `python main.py approve --lecture <id>` | Validate the script, dry-run its code and approve it |
| `python main.py render --lecture <id>` | Pre-render narration audio with Gnani TTS |
| `python main.py session --lecture <id>` | Run the lesson in the terminal, with doubts |
| `python main.py doubts --lecture <id>` | Test a doubt checkpoint |
| `python main.py status --lecture <id>` | Show the lecture's status |
| `python main.py measure-voice` | Measure the voice's speaking rate and save it to `.env` |
| `python main.py tutor-video` | Build the classroom video tutor from an idle and a talking clip |

## Script format

An approved script is plain text with inline markers, parsed by `eris/generate/script_parser.py`. Narration sits between the markers. Adding `while_speaking=true` runs an action during the next line instead of before it.

| Marker | Action |
|---|---|
| `[SECTION title="..."]` | Starts a section of the lesson |
| `[SLIDE n=3]` | Shows a slide |
| `[SLIDE_HIGHLIGHT n=3 text="..."]`, `[SLIDE_CIRCLE n=3 part="..."]` | Highlights a line or circles a part of a slide |
| `[BOOK page=14]` | Opens a textbook page |
| `[BOOK_HIGHLIGHT page=14 text="..."]`, `[BOOK_UNDERLINE ...]`, `[BOOK_CIRCLE ...]` | Marks text on the page |
| `[BOOK_EXAMPLE page=14 name="..."]`, `[BOOK_ANSWER ...]` | Works a book example with the answer hidden, then reveals it |
| `[NOTE_TITLE text="..."]`, `[NOTE] ... [/NOTE]`, `[NOTE_HIGHLIGHT text="..."]` | Writes and highlights in the notebook |
| `[WRITE_CODE file="..."] ... [/WRITE_CODE]`, `[RUN cmd="..."]`, `[READ_OUTPUT]` | Types, runs and reads a program |
| `[FLOW id="..." title="..."]`, `[FLOW_NEXT id="..."]` | Draws a flow diagram step by step |
| `[VISUAL id="..." title="..."]`, `[VISUAL_SET id="..." control="..." value=45]` | Shows an interactive graph and moves its controls |
| `[DOUBT_CHECK]` | Pauses for students' questions |

## Project structure

```
Eris/
├── main.py            CLI entry point
├── eris/
│   ├── config.py      Settings and lecture paths
│   ├── prompts.py     Prompts for the planner, writer, stager, judge and doubt agent
│   ├── material/      Ingestion: PDF, PPTX and DOCX parsing, vision, figures, slides
│   ├── generate/      Script pipeline: planning, writing, staging, checks and fixes
│   ├── visuals/       Flow diagrams and interactive graphs
│   ├── classroom/     Session player, doubt agent and voice
│   ├── platform/      Accounts, courses, attendance and demo seeding
│   └── api/           FastAPI server and background jobs
├── web/               Frontend (HTML, CSS, JavaScript, Three.js avatar)
├── templates/         Persona template and demo lessons
├── deploy/            Caddy configuration and deployment guides
└── docs/              Design notes
```

## Troubleshooting

| Problem | Fix |
|---|---|
| The model does not call tools | Use an `LLM_MODEL` that supports tool calling on OpenRouter. |
| A script fails approval | Check `workspace/lectures/<id>/script_failed.md`, fix `script.md`, and run `approve` again. |
| Slides appear as text, not images | Install LibreOffice (`soffice`) to render PPTX decks. PDF decks need nothing extra. |
| Code lessons cannot run programs | Start Docker and run `docker pull python:3.12-slim`, or set `ERIS_SANDBOX=os` on macOS or Linux. |
| No voice in the classroom | Gnani is optional. Without `GNANI_API_KEY`, the browser's speech synthesis is used. |
| "This is a teacher account" on sign-in | Choose the matching role (teacher or student) on the sign-in page. |

## License

Copyright (c) 2026 the Eris authors. All rights reserved.

This code is proprietary. No part of it may be copied, modified, distributed or used without written permission from the authors.
