"""Flow diagrams the teacher draws on the board block by block. No LLM here.

The script writes the structure only; our code (web/js/flow.js) draws it, top to bottom, the same way every time:

    [FLOW id="for-loop" title="How a for loop runs" from="slide 2"]
    take: Take the next item
    body: Run the loop body
    more: Any items left? | yes -> take | no -> end
    [/FLOW]
    [FLOW_NEXT id="for-loop"]          draws the next block (and its arrows), in the order listed
    [FLOW_HIGHLIGHT id="for-loop" block="more"]   points back at a block already drawn
    [OPEN_FLOW id="for-loop"]          shows the diagram again

One line per block: "id: label" (the id is optional). A label ending in "?" is a question (a diamond); its
branches follow "|" as "answer -> target", where target is a block id or "end". A block without branches
leads to the next line. parse_flow(body) returns (blocks, edges, problems).
"""

import re

LINE_RE = re.compile(r"^(?:([a-z][a-z0-9_-]{0,19})\??\s*:\s+)?(.+)$")  # "more?:" is read as id "more"
BRANCH_RE = re.compile(r"^\s*([^>]+?)\s*->\s*([A-Za-z][\w-]*)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
MAX_BLOCKS = 8
MAX_LABEL = 60
FLOW_HELP = ('write one block per line, exactly like this:\n'
             '  take: Take the next item\n'
             '  body: Run the loop body\n'
             '  more: Any items left? | yes -> take | no -> end\n'
             '(id, colon, label; a question ends its label with "?" and lists its branches after "|")')


def parse_flow(body):
    """Blocks [{id, label, kind: "step" | "question"}] and edges [{from, to, label}] from a [FLOW] body."""
    blocks, branches, problems = [], [], []
    for raw in body.splitlines():
        line = BULLET_RE.sub("", raw).strip()
        if not line:
            continue
        head, *rest = [p.strip() for p in line.split("|")]
        m = LINE_RE.match(head)
        if not m or not m.group(2).strip():
            problems.append(f"cannot read the block '{raw.strip()}'; {FLOW_HELP}")
            continue
        bid = m.group(1) or f"b{len(blocks) + 1}"
        label = m.group(2).strip()
        if any(b["id"] == bid for b in blocks):
            problems.append(f"block id '{bid}' is used twice")
            continue
        if len(label) > MAX_LABEL:
            problems.append(f"block '{bid}' is too long ({len(label)} characters); keep labels under {MAX_LABEL}")
        kind = "question" if label.endswith("?") else "step"
        outs = []
        for part in rest:
            b = BRANCH_RE.match(part)
            if not b:
                problems.append(f"cannot read the branch '{part}' of block '{bid}'; write branches like "
                                "'| yes -> take | no -> end' (an answer, '->', then a block id or end)")
            else:
                outs.append({"from": bid, "to": b.group(2).lower(), "label": b.group(1).strip()})
        if outs and kind != "question":  # it branches, so it is a question even if its "?" was left out or misplaced
            kind, label = "question", label.rstrip(".") + "?"
        blocks.append({"id": bid, "label": label, "kind": kind})
        branches.append(outs)
    if not blocks and not problems:
        problems.append(f"the flow has no blocks; {FLOW_HELP}")
    if len(blocks) > MAX_BLOCKS:
        problems.append(f"the flow has {len(blocks)} blocks; keep it to {MAX_BLOCKS} or fewer (one per idea)")
    ids = {b["id"] for b in blocks} | {"end"}
    edges = []
    for i, (block, outs) in enumerate(zip(blocks, branches)):
        for e in outs:
            if e["to"] not in ids:
                ids_list = ", ".join(b["id"] for b in blocks)
                problems.append(f"block '{block['id']}' points to '{e['to']}', which is not a block id; use one of: "
                                f"{ids_list}, or end")
            else:
                edges.append(e)
        if not outs and i + 1 < len(blocks):
            edges.append({"from": block["id"], "to": blocks[i + 1]["id"], "label": ""})
    return blocks, edges, problems


def describe_flow(flow):
    """One readable line per block, for the board and prompts."""
    lines = []
    for b in flow["blocks"]:
        outs = [f'{e["label"]} -> {e["to"]}' for e in flow.get("edges", []) if e["from"] == b["id"] and e["label"]]
        lines.append(f'{b["id"]}: {b["label"]}' + (f' | {" | ".join(outs)}' if outs else ""))
    return "\n".join(lines)
