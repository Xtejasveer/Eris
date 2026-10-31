# 🎓 Eris — AI Substitute Teacher Platform

> **Autonomous, pedagogical AI teaching assistant that transforms course materials into interactive, synchronized classroom lectures with 3D avatars, dynamic stages, and live doubt resolution.**

[![Live Demo](https://img.shields.io/badge/Live_Demo-Eris_on_Azure-1b6e66?style=for-the-badge&logo=azure&logoColor=white)](https://eris.indiasouthcentral.cloudapp.azure.com/#/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Three.js](https://img.shields.io/badge/Three.js-WebGL_Avatar-black?style=for-the-badge&logo=three.js&logoColor=white)](https://threejs.org/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

---

### 🌐 Live Deployment

Experience the live platform directly in your browser:  
👉 **[https://eris.indiasouthcentral.cloudapp.azure.com/#/](https://eris.indiasouthcentral.cloudapp.azure.com/#/)**

---

## 💡 Overview

Eris addresses teacher absence and prerequisite gaps by turning teacher slides, documents, and teaching style into an interactive, student-centered class session:

1. **Teacher Control First**: The LLM writes the complete lesson script once; the teacher reviews, edits, and approves it before any class starts.
2. **Deterministic Player (No Drift)**: In class, a plain-code player walks the approved `script.json` sequentially. Narration and board actions are strictly synchronized: speech never gets ahead of the writing or code execution.
3. **Multi-Modal Classroom Stage**: Automatically coordinates four live environments: ruled handwritten **Notebook**, presentation **Slides**, interactive **Code Editor & Terminal**, and dynamic **Visual Boards** (flowcharts and graphs with live sliders).
4. **Interactive 3D Avatar**: Browser-based Three.js avatar with real-time Web Audio API viseme lip-sync, blinking, gaze saccades, and expressive moods—running completely client-side without GPU server overhead.
5. **Context-Aware Doubt Agent**: Students can ask questions anytime via text or voice. An autonomous LangGraph agent inspects the read-only board state, references indexed course materials, and can write code or draw diagrams live to explain answers.
6. **Per-Student Device Sessions**: Students learn at their own pace on their own devices with exact attendance tracking based on segments actively watched.

```
┌────────────────────────┐      ┌─────────────────────────┐      ┌────────────────────────┐
│  Teacher Materials     │ ───► │  Script Generation &    │ ───► │  Interactive Class     │
│  • PPTX, PDF, DOCX     │      │  Quality Verification   │      │  • 3D Talking Avatar   │
│  • Teacher Persona     │      │  • Strict Parser        │      │  • Synchronized Stage  │
│  • Vision OCR & Schema │      │  • Code Dry-Runs        │      │  • Live Doubt Agent    │
│  • ChromaDB Index      │      │  • Teacher Approval     │      │  • Audio Pre-render    │
└────────────────────────┘      └─────────────────────────┘      └────────────────────────┘
```

---

## 🏛️ System Architecture

The following diagram illustrates the complete workflow from ingestion to classroom execution and deployment:

```mermaid
graph TB
    subgraph Ingestion ["1. Material Ingestion & Indexing"]
        Files["Teacher Files<br/>(PPTX, PDF, DOCX)"]
        Persona["Teacher Persona<br/>(persona.md)"]
        Vision["Vision Model<br/>(OCR + Image Descriptions)"]
        Indexer["Indexer Engine<br/>(eris/material/)"]
        Chroma[("ChromaDB<br/>Vector Store")]
        Figures["Extracted Figures<br/>(figures.json)"]

        Files --> Indexer
        Persona --> Indexer
        Files --> Vision --> Indexer
        Indexer --> Chroma
        Indexer --> Figures
    end

    subgraph Generation ["2. Generation & Verification Pipeline"]
        ScriptAgent["Script Agent<br/>(Outline & Writer)"]
        Validator["Pipeline Validator<br/>(Dry-run & Fixers)"]
        Judge["Quality Judge Loop<br/>(Pacing & Pedagogy)"]
        ScriptMD["script.md / script.json<br/>(Deterministic Segments)"]
        Approval{"Teacher Approval<br/>(Studio Review)"}
        TTS["Voice Pre-renderer<br/>(Gnani Timbre v2.5)"]
        AudioCache[("Audio Cache<br/>WAV Clips")]

        Chroma & Figures --> ScriptAgent
        ScriptAgent --> Validator --> Judge --> ScriptMD
        ScriptMD --> Approval
        Approval -->|Approved| TTS --> AudioCache
    end

    subgraph Classroom ["3. Classroom Runtime & Doubt Handling"]
        Player["Deterministic Player<br/>(Narration + Action Sync)"]
        Avatar["3D Avatar Engine<br/>(Three.js + FFT Lip-Sync)"]
        Stage["Classroom Stage<br/>(Notebook | Slides | Code | Visuals)"]
        Student["Student<br/>(Voice / Text Doubts)"]
        DoubtAgent["Doubt Agent<br/>(LangGraph + Tools)"]
        Sandbox["Docker Sandbox<br/>(Code Execution)"]

        AudioCache & ScriptMD --> Player
        Player --> Avatar
        Player --> Stage
        Student --> DoubtAgent
        Stage -.->|Read-only Snapshot| DoubtAgent
        Chroma -.->|Semantic Search| DoubtAgent
        DoubtAgent --> Sandbox
        DoubtAgent -->|Live Answer + Board Update| Stage
    end

    subgraph Deployment ["4. Cloud Infrastructure"]
        Azure["Azure VM (Standard_B2s)<br/>Ubuntu 24.04 LTS"]
        Caddy["Caddy Reverse Proxy<br/>Auto HTTPS / SSL"]
        FastAPI["FastAPI App Server<br/>(eris:8000)"]

        Caddy --> FastAPI
        FastAPI --> Classroom
    end

    classDef ing fill:#e1f5fe,stroke:#0288d1,stroke-width:1.5px;
    classDef gen fill:#ede7f6,stroke:#512da8,stroke-width:1.5px;
    classDef cls fill:#e8f5e9,stroke:#2e7d32,stroke-width:1.5px;
    classDef dep fill:#fff3e0,stroke:#e65100,stroke-width:1.5px;

    class Files,Persona,Vision,Indexer,Chroma,Figures ing;
    class ScriptAgent,Validator,Judge,ScriptMD,Approval,TTS,AudioCache gen;
    class Player,Avatar,Stage,Student,DoubtAgent,Sandbox cls;
    class Azure,Caddy,FastAPI dep;
```

---

## 🖥️ The 4 Classroom Environments

The stage intelligently switches between four dedicated teaching environments based on the course material:

| Environment | Purpose | When Used |
|---|---|---|
| **📝 Notebook** | Ruled blackboard with hand-drawn cursive writing, section headers, and inline highlights. | Always active as the primary whiteboard. |
| **📑 Slides** | Slide viewer showing slides alongside vision-extracted diagrams, charts, and captions. | Unlocked when presentation decks (PPTX) exist. |
| **💻 Code Editor** | Syntax-highlighted code editor with live terminal output and verified execution. | Unlocked when course files contain programming code. |
| **📊 Visual Board** | Step-by-step whiteboard flowcharts and interactive graphs with real-time sliders. | Unlocked when processes or mathematical charts exist. |

---

## ⚡ Quick Start

### 1. Prerequisites
- **Python 3.12**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or standard `pip`
- **[OpenRouter](https://openrouter.ai)** API key (with a tool-calling model such as `openai/gpt-4o-mini`)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/Xtejasveer/Eris.git
cd Eris

# Create and activate virtual environment
uv venv --python 3.12
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
uv pip install -r requirements-extras.txt  # Optional: photorealistic video avatar & faster-whisper

# Setup environment variables
cp .env.example .env
```

### 3. Configure Environment

Edit `.env` with your credentials:

```ini
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL=openai/gpt-4o-mini
GNANI_API_KEY=your_gnani_api_key          # Optional: provides high-fidelity Indian English TTS/STT
```

> [!NOTE]
> If `GNANI_API_KEY` is not provided, Eris automatically falls back to the browser's built-in speech synthesis engine.

### 4. Run the Web Application

```bash
python main.py serve
```

Open your browser at **[http://127.0.0.1:8000](http://127.0.0.1:8000)**:
- **Studio (Home)**: Upload materials, configure teacher persona, generate script, and click **Approve**.
- **Classroom**: Click **Start class** to experience the interactive lecture, avatar, and live doubt Q&A.

---

## 🐳 Docker Deployment

Run the complete production stack (Eris + Caddy with automatic SSL):

```bash
docker compose up -d --build
```

For full Azure VM setup and custom domain configuration, see [deploy/azure.md](file:///d:/Eris/deploy/azure.md).

---

## ⌨️ Command Line Interface

Eris can also be completely managed and executed through the terminal:

| Command | Description |
|---|---|
| `python main.py serve` | Start the web application server (`http://127.0.0.1:8000`). |
| `python main.py index --lecture <id>` | Build knowledge base and figures index from `data/<id>/`. |
| `python main.py generate --lecture <id>` | Write lesson outline and script (`status: draft`). |
| `python main.py approve --lecture <id>` | Validate script, dry-run code blocks, and approve (`status: approved`). |
| `python main.py render --lecture <id>` | Pre-render narration audio clips with Gnani TTS. |
| `python main.py session --lecture <id>` | Run the interactive terminal classroom session. |
| `python main.py doubts --lecture <id>` | Test doubt agent checkpoints against full topic context. |
| `python main.py status --lecture <id>` | Display current manifest status and statistics. |

---

## 🏷️ Script Markers Cheat Sheet

Scripts use clean inline markers parsed by `eris/generate/script_parser.py`:

| Marker | Description | Example |
|---|---|---|
| `[NOTE]` | Writes handwritten lines onto the notebook page. | `[NOTE]\nRepeats while condition is True\n[/NOTE]` |
| `[NOTE_TITLE]` | Underlined heading in the notebook. | `[NOTE_TITLE text="While Loops"]` |
| `[NOTE_HIGHLIGHT]` | Yellow highlighter over existing notebook text. | `[NOTE_HIGHLIGHT text="condition is True"]` |
| `[WRITE_CODE]` | Types code into the classroom code editor. | `[WRITE_CODE file="demo.py"]\nprint("Hello")\n[/WRITE_CODE]` |
| `[RUN]` | Executes a file in the code terminal. | `[RUN cmd="python demo.py"]` |
| `[READ_OUTPUT]` | Validates terminal output against expected result. | `[READ_OUTPUT]\nHello\n[/READ_OUTPUT]` |
| `[SLIDE]` | Displays a specific slide from the presentation deck. | `[SLIDE num=3]` |
| `[FLOW]` | Draws a block-by-block whiteboard flowchart. | `[FLOW id="loop" title="Loop Flow"]\nstep: Do work\n[/FLOW]` |
| `[VISUAL]` | Interactive graph with real-time sliders. | `[VISUAL id="chart" title="Distribution"]\ncontrols: mean (slider 0-10)\n[/VISUAL]` |
| `[DOUBT_CHECK]` | Pauses the lecture for student questions. | `[DOUBT_CHECK]` |
| `while_speaking=true` | Types code or notes *simultaneously* while speaking. | `[WRITE_CODE file="sum.py" while_speaking=true]` |

---

## 📁 Repository Structure

```
Eris/
├── main.py                     # CLI entry point (serve, index, generate, approve, render, session)
├── eris/                       # Core Python package
│   ├── config.py               # Settings, environment paths, and lecture manifest
│   ├── persona.py              # Teacher persona parser
│   ├── prompts.py              # System prompts for researcher, writer, judge, and doubt agents
│   ├── material/               # Ingestion: PDF/PPTX/DOCX indexer, vision OCR, figure extractor
│   ├── generate/               # Script pipeline: outline writer, parser, validator, and quality judge
│   ├── visuals/                # Visual board: flowchart renderer and interactive graph builders
│   ├── classroom/              # Class execution: doubt agent, session player, voice engine, actions
│   └── api/                    # Web backend: FastAPI server, classroom endpoints, and job runners
├── web/                        # Frontend application (Vanilla HTML/CSS/JS, Three.js avatar)
│   ├── css/                    # Studio, classroom, and base design styles
│   ├── js/                     # Client player, stage controllers, avatar engine, visual runtime
│   └── assets/                 # 3D GLB avatar models and audio demo assets
├── deploy/                     # Production deployment: Caddy reverse proxy, Azure guide
├── templates/                  # Example persona templates (templates/persona.md)
└── docs/                       # Architectural design notes and implementation plans
```

---

## 🔧 Common Troubleshooting

<details>
<summary><b>Model does not call tools / returns tool error</b></summary>
Ensure <code>LLM_MODEL</code> supports tool-calling on OpenRouter (e.g., <code>openai/gpt-4o-mini</code> or <code>anthropic/claude-3.5-sonnet</code>).
</details>

<details>
<summary><b>Script fails approval validation</b></summary>
Inspect <code>workspace/lectures/<id>/script_failed.md</code> for syntax issues or code mismatch errors. Edit <code>script.md</code> to fix the lines, then run <code>python main.py approve --lecture <id></code>.
</details>

<details>
<summary><b>Audio not playing / No Gnani API key</b></summary>
Gnani TTS is optional. Without <code>GNANI_API_KEY</code>, the web classroom automatically uses the browser's native Web Speech synthesis.
</details>

---

## 📄 License

This project is licensed under the MIT License.
