#!/usr/bin/env python3
"""Builds the playground web page.

    docs/playground.src.html + js/loma.js + examples/*.loma  ->  docs/index.html

docs/index.html is a single self-contained file: open it in a browser or serve it with GitHub Pages.
With --body PATH the page is also written without the outer document skeleton, for hosts that add
their own.

    python3 tools/build_web.py
    python3 tools/build_web.py --check        # exit 1 if docs/index.html is out of date
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXAMPLES = [("First example", None), ("Brano 1 - Lanterna", "brano1.loma"), ("Brano 2 - Mulino", "brano2.loma"),
            ("Brano 3 - Faro", "brano3.loma"), ("Showcase", "showcase.loma")]

SITE = "https://manuellomartire.github.io/loma/"
DESCRIPTION = ("Write music as text and hear it: LOMA is a language made for AIs that always compiles "
               "to the same MIDI file, byte for byte. Editor, piano roll and MIDI converter in the browser.")
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%23111'/%3E"
        "%3Cpath d='M5 3v10h7' fill='none' stroke='%23fff' stroke-width='2'/%3E%3C/svg%3E")
SKELETON = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            '<title>LOMA Playground</title>\n'
            '<meta name="description" content="' + DESCRIPTION + '">\n'
            '<link rel="canonical" href="' + SITE + '">\n'
            '<link rel="icon" href="' + ICON + '">\n'
            '<meta property="og:type" content="website">\n'
            '<meta property="og:title" content="LOMA Playground">\n'
            '<meta property="og:description" content="' + DESCRIPTION + '">\n'
            '<meta property="og:url" content="' + SITE + '">\n'
            '<meta property="og:image" content="' + SITE + 'og.png">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>\n'
            '</head>\n<body>\n@@PAGE@@</body>\n</html>\n')


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def body():
    readme = read("README.md")
    first = re.search(r"```loma\n(.*?)```", readme, re.S).group(1)
    examples = [{"name": name, "source": first if path is None else read("examples", path)} for name, path in EXAMPLES]
    compiler = read("js", "loma.js")
    if compiler.startswith("#!"):
        compiler = compiler.split("\n", 1)[1]
    for text in (compiler, json.dumps(examples)):
        if "</script" in text.lower():
            raise SystemExit("the embedded text contains a closing script tag")
    page = read("docs", "playground.src.html")
    for marker in ("/*__LOMA_JS__*/", "/*__EXAMPLES__*/"):
        if page.count(marker) != 1:
            raise SystemExit("marker %s must appear exactly once in docs/playground.src.html" % marker)
    page = page.replace("/*__LOMA_JS__*/", compiler)
    return page.replace("/*__EXAMPLES__*/", json.dumps(examples, ensure_ascii=False).replace("</", "<\\/"))


def main():
    ap = argparse.ArgumentParser(description="Build docs/index.html")
    ap.add_argument("--check", action="store_true", help="do not write; fail if docs/index.html is out of date")
    ap.add_argument("--body", help="also write the page without the document skeleton to this path")
    args = ap.parse_args()
    content = body()
    full = SKELETON.replace("@@PAGE@@", content)
    target = os.path.join(ROOT, "docs", "index.html")
    if args.check:
        current = read("docs", "index.html") if os.path.exists(target) else ""
        if current != full:
            print("docs/index.html is out of date: run python3 tools/build_web.py")
            return 1
        return 0
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(full)
    if args.body:
        with open(args.body, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print("wrote %s (%d bytes)" % (os.path.relpath(target, ROOT), len(full.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
