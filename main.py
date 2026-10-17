"""CLI entry point: serve (website) / index / generate / approve / render / session (+ doubts, status)."""

import argparse
import json
import re
import sys

import config

# Chroma collection names: 3-63 chars, letters/digits/_/-, start and end with a letter or digit.
LECTURE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$")


def run_approve(lecture_id):
    from script_writer import approve_script

    errors = approve_script(lecture_id)
    if errors:
        print(f"[approve] Approval refused. Fix these {len(errors)} error(s) in script.md:")
        for e in errors:
            print("  " + e)
        sys.exit(1)
    print(f"Approved. Start the class with: python main.py session --lecture {lecture_id}")


def run_doubts_test(lecture_id):
    """One checkpoint with the whole topic as context (for testing the doubt agent)."""
    from doubt_agent import run_checkpoint
    from session import start_doubts

    manifest = config.load_manifest(lecture_id)
    agent, log_path = start_doubts(lecture_id, manifest)
    context = (f"The whole lecture on '{manifest['topic']}' has been taught. "
               "Now ask the class for doubts.")
    asked, passed = run_checkpoint(agent, f"doubts_test_{lecture_id}", context,
                                   config.MAX_DOUBTS_FINAL, log_path)
    print(f"\n[doubts] asked: {asked}, passed to teacher: {passed}, log: {log_path}")


def run_render(lecture_id):
    """Pre-render narration audio with Gnani TTS and record the real lecture length."""
    config.check_voice_env()
    import voice

    manifest = config.load_manifest(lecture_id)
    script_json = config.lecture_dir(lecture_id) / "script.json"
    if not script_json.exists():
        print("[render] No script.json. Run generate and approve first.")
        sys.exit(1)
    segments = json.loads(script_json.read_text(encoding="utf-8"))
    seconds, failures = voice.render_lecture(lecture_id, segments)
    runs = sum(1 for s in segments if s.get("name") == "RUN")
    pauses = sum(s["args"]["s"] for s in segments if s.get("name") == "PAUSE")
    manifest["audio_min"] = round(seconds / 60, 1)
    manifest["estimated_min"] = round(seconds / 60 + runs * config.RUN_MIN_EACH + pauses / 60, 1)
    config.save_manifest(lecture_id, manifest)
    print(f"[render] narration {manifest['audio_min']} min, lecture about {manifest['estimated_min']} min"
          f" (target {manifest['duration_min']}); {failures} clip(s) failed")


def build_parser():
    parser = argparse.ArgumentParser(description="AI Substitute Teacher v1")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("index", help="build the knowledge base from data/<id>/")
    p.add_argument("--lecture", required=True)
    p.add_argument("--query", help="only run a test search")
    p.add_argument("--no-reset", action="store_true", help="keep the existing collection")

    for name, text in [("generate", "write the script (status: draft)"),
                       ("approve", "validate script.md and approve it"),
                       ("doubts", "test one doubt checkpoint"),
                       ("render", "pre-render narration audio (Gnani TTS)"),
                       ("status", "print lecture.json")]:
        sub.add_parser(name, help=text).add_argument("--lecture", required=True)

    p = sub.add_parser("serve", help="start the website (home + class)")
    p.add_argument("--port", type=int, default=8000)

    p = sub.add_parser("session", help="run the approved lecture with doubts")
    p.add_argument("--lecture", required=True)
    p.add_argument("--force", action="store_true", help="run even if not approved")
    p.add_argument("--voice", action="store_true", help="speak narration and answers (Gnani TTS)")
    p.add_argument("--mic", action="store_true", help="let students speak their doubts (Gnani STT)")
    p.add_argument("--resume", action="store_true", help="continue a paused session")
    return parser


def main():
    args = build_parser().parse_args()
    if args.command == "serve":
        config.check_env()
        import uvicorn
        print(f"Open http://127.0.0.1:{args.port}")
        uvicorn.run("server:app", host="127.0.0.1", port=args.port)
        return
    if not LECTURE_ID_RE.match(args.lecture):
        print(f"Bad lecture id '{args.lecture}'. Use 3-63 letters, digits, _ or -, e.g. py_listcomp_2026_10_17")
        sys.exit(1)

    if args.command == "status":
        print(json.dumps(config.load_manifest(args.lecture), indent=2, ensure_ascii=False))
        return

    config.check_env()
    # Imports happen here so `status` and bad-argument errors stay fast.
    if args.command == "index":
        from indexer import run_index, test_query
        if args.query:
            test_query(args.lecture, args.query)
        else:
            run_index(args.lecture, reset=not args.no_reset)
    elif args.command == "generate":
        from script_writer import run_generate
        run_generate(args.lecture)
    elif args.command == "approve":
        run_approve(args.lecture)
    elif args.command == "session":
        from session import run_session
        run_session(args.lecture, force=args.force, use_voice=args.voice,
                    use_mic=args.mic, resume=args.resume)
    elif args.command == "render":
        run_render(args.lecture)
    elif args.command == "doubts":
        run_doubts_test(args.lecture)


if __name__ == "__main__":
    main()
