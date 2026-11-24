#!/usr/bin/env python3
"""Generate Sileo depiction JSON from descriptions/<Package>.md.

For each <Package>.md in descriptions/, produces depictions/<Package>.json
containing a simple "body" HTML rendering. Markdown-lite rules:
  lines starting with "## " -> <h2>, "### " -> <h3>
  "- **X** — Y"              -> <li><strong>X</strong> — Y
  "---" alone                -> <hr>
  other lines                -> <p>
No external deps. gen_packages.py auto-adds Depiction field when JSON exists.
"""

import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DESC_DIR = os.path.join(ROOT, "descriptions")
OUT_DIR = os.path.join(ROOT, "depictions")


def render(md_text):
    out = []
    for raw in md_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "---":
            out.append("<hr>")
            continue
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            tag = "h2" if len(m.group(1)) == 2 else "h3"
            out.append("<%s>%s</%s>" % (tag, html.escape(m.group(2)), tag))
            continue
        m = re.match(r"^-\s+\*\*(.+?)\*\*\s*[—-]\s*(.*)$", line)
        if m:
            out.append("<li><strong>%s</strong> — %s</li>" % (
                html.escape(m.group(1)), html.escape(m.group(2))))
            continue
        if line.startswith("- "):
            out.append("<li>%s</li>" % html.escape(line[2:]))
            continue
        out.append("<p>%s</p>" % html.escape(line))
    return "\n".join(out)


def main():
    if not os.path.isdir(DESC_DIR):
        print("descriptions/ directory missing", file=sys.stderr)
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    files = sorted(f for f in os.listdir(DESC_DIR) if f.endswith(".md"))
    if not files:
        print("no descriptions/*.md found; nothing to generate")
        return

    for fn in files:
        pkg = fn[:-3]
        md = open(os.path.join(DESC_DIR, fn), encoding="utf-8").read()
        data = {
            "title": pkg,
            "body": render(md),
        }
        with open(os.path.join(OUT_DIR, pkg + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print("generated depictions/%s.json" % pkg)


if __name__ == "__main__":
    main()
