"""Build one PDF of the whole documentation (docs/*.md and docs/reference/*.md).

Usage: python docs/build_docs_pdf.py [--out docs/DLTS_Software_Documentation.pdf] [--html page.html]

The Markdown pages are converted with mistune, in the order of docs/README.md:
overview, the four guides, then one reference page per module. Links between
pages become links inside the PDF, images are embedded, and the Mermaid diagram
is drawn with mermaid.js (downloaded once from jsDelivr; without network the
diagram's source is printed instead). The page is printed with headless
Microsoft Edge, with page numbers in the footer. --html also saves the
intermediate page for inspection.
"""
import argparse, base64, html, mimetypes, os, posixpath, re, subprocess, tempfile, time, urllib.request
from datetime import date
import mistune

DOCS = os.path.dirname(os.path.abspath(__file__))
ORDER = [
    ('README.md', 'Overview'),
    ('getting_started.md', 'Guide'), ('running_a_dlts_experiment.md', 'Guide'),
    ('quick_run.md', 'Guide'), ('standalone_instruments.md', 'Guide'),
    ('reference/DLTSGUI_MainWindow.md', 'Reference'), ('reference/runParamsTab.md', 'Reference'),
    ('reference/liveDataTab.md', 'Reference'), ('reference/dataAnalysisTab.md', 'Reference'),
    ('reference/detailedAnalysisTab.md', 'Reference'), ('reference/runDlts_Tools.md', 'Reference'),
    ('reference/zurichInstruments_Control.md', 'Reference'), ('reference/instecTempStage_Control.md', 'Reference'),
    ('reference/impedanceAnalysis_Tools.md', 'Reference'), ('reference/dltsConfig.md', 'Reference'),
    ('reference/convert_json_to_h5.md', 'Reference'), ('reference/convert_h5_to_text.md', 'Reference'),
    ('reference/data_formats.md', 'Reference'), ('reference/other_scripts.md', 'Reference'),
]
MERMAID_URL = 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js'
EDGE = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']


def doc_id(rel):
    return 'doc-' + posixpath.splitext(posixpath.basename(rel))[0]


def slug(text):
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r'<[^>]+>', '', html.unescape(text)).strip().lower()
    return re.sub(r'\s', '-', re.sub(r'[^\w\- ]', '', text))


class Renderer(mistune.HTMLRenderer):
    def __init__(self, rel, known):
        super().__init__(escape=False)
        self.rel, self.known, self.seen, self.headings = rel, known, {}, []

    def heading(self, text, level, **attrs):
        s = slug(text)
        n = self.seen.get(s, 0); self.seen[s] = n + 1
        hid = f'{doc_id(self.rel)}--{s}' + (f'-{n}' if n else '')
        if level == 1:
            hid = doc_id(self.rel)
        self.headings.append((level, text, hid))
        return f'<h{level} id="{hid}">{text}</h{level}>\n'

    def block_code(self, code, info=None):
        if info and info.strip().lower() == 'mermaid':
            return f'<pre class="mermaid">{html.escape(code)}</pre>\n'
        return f'<pre><code>{html.escape(code)}</code></pre>\n'

    def link(self, text, url, title=None):
        if re.match(r'^[a-z]+:', url):                       # http(s), mailto: keep
            return f'<a href="{html.escape(url)}">{text}</a>'
        path, _, anchor = url.partition('#')
        if not path:                                          # same page
            return f'<a href="#{doc_id(self.rel)}--{anchor}">{text}</a>'
        target = posixpath.normpath(posixpath.join(posixpath.dirname(self.rel), path))
        if target in self.known:
            return f'<a href="#{doc_id(target)}' + (f'--{anchor}' if anchor else '') + f'">{text}</a>'
        # A repository file outside the docs (script, benchmark report): name it, no link.
        return f'{text} <span class="path">({html.escape(posixpath.normpath(posixpath.join("docs", posixpath.dirname(self.rel), path)))})</span>'

    def image(self, text, url, title=None):
        p = os.path.normpath(os.path.join(DOCS, os.path.dirname(self.rel), url))
        if os.path.exists(p):
            mime = mimetypes.guess_type(p)[0] or 'image/png'
            url = f'data:{mime};base64,' + base64.b64encode(open(p, 'rb').read()).decode()
        return f'<figure><img src="{url}" alt="{html.escape(text)}"><figcaption>{text}</figcaption></figure>'


CSS = """
@page { size: Letter; margin: 16mm 15mm 18mm 15mm;
  @bottom-right { content: counter(page) " / " counter(pages); font: 9pt "Segoe UI", sans-serif; color: #7d827b; }
  @bottom-left { content: "DLTS control software: documentation"; font: 9pt "Segoe UI", sans-serif; color: #7d827b; } }
@page :first { @bottom-right { content: none; } @bottom-left { content: none; } }
body { font: 10pt/1.5 "Segoe UI", system-ui, sans-serif; color: #111412; margin: 0; }
h1 { font-size: 22pt; line-height: 1.15; margin: 0 0 6pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; border-bottom: 1px solid #c3c6be; padding-bottom: 2pt; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
h4 { font-size: 10.5pt; margin: 12pt 0 4pt; }
h2, h3, h4 { break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #1c5cab; text-decoration: none; }
code { font: 8.8pt Consolas, "Cascadia Mono", monospace; background: #f1f2ee; padding: 0 2px; border-radius: 2px; overflow-wrap: anywhere; }
pre { font: 8.3pt/1.4 Consolas, "Cascadia Mono", monospace; background: #f4f5f2; border: 1px solid #e1e3dd;
      border-radius: 4px; padding: 6pt 8pt; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
pre code { background: none; padding: 0; font: inherit; }
pre.mermaid { background: none; border: none; text-align: center; white-space: pre; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.5pt; }
th, td { border: 1px solid #d0d2cb; padding: 3pt 5pt; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
th { background: #eef0eb; font-weight: 600; }
tr { break-inside: avoid; }
figure { margin: 8pt 0; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 190mm; border: 1px solid #e1e3dd; }
figcaption { font-size: 8.5pt; color: #50554f; margin-top: 3pt; }
blockquote { border-left: 3px solid #c3c6be; margin: 6pt 0; padding: 0 10pt; color: #50554f; }
.path { font: 8.5pt Consolas, monospace; color: #50554f; }
.doc { break-before: page; }
.part { font: 600 8.5pt "Segoe UI", sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #7d827b; margin-bottom: 2pt; }
.cover { height: 230mm; display: flex; flex-direction: column; justify-content: center; }
.cover h1 { font-size: 34pt; margin-bottom: 10pt; }
.cover .sub { font-size: 13pt; color: #50554f; max-width: 34em; }
.cover .meta { margin-top: 28pt; font-size: 10pt; color: #7d827b; }
.toc { break-before: page; }
.toc ol { padding-left: 16pt; } .toc li { margin: 2pt 0; }
.toc ul { list-style: none; padding-left: 10pt; font-size: 9pt; }   /* the guides' own headings carry their numbers */
"""


def build_html(mermaid_js):
    known = {rel for rel, _ in ORDER}
    parts, toc = [], []
    for rel, part in ORDER:
        src = open(os.path.join(DOCS, rel), encoding='utf-8').read()
        r = Renderer(rel, known)
        body = mistune.create_markdown(renderer=r, plugins=['table', 'strikethrough', 'url'])(src)
        parts.append(f'<section class="doc"><div class="part">{part}</div>{body}</section>')
        title = next((t for lvl, t, _ in r.headings if lvl == 1), rel)
        subs = [(t, h) for lvl, t, h in r.headings if lvl == 2] if part != 'Reference' else []
        toc.append((part, title, doc_id(rel), subs))
    tocHtml, lastPart = [], None
    for part, title, did, subs in toc:
        if part != lastPart:
            if lastPart is not None:
                tocHtml.append('</ol>')
            tocHtml.append(f'<h3>{part}</h3><ol>'); lastPart = part
        tocHtml.append(f'<li><a href="#{did}">{title}</a>' +
                       ('<ul>' + ''.join(f'<li><a href="#{h}">{t}</a></li>' for t, h in subs) + '</ul>' if subs else '')
                       + '</li>')
    tocHtml.append('</ol>')
    script = ''
    if mermaid_js:
        script = ('<script>' + mermaid_js.replace('</script', '<\\/script') + '</script>'
                  "<script>mermaid.initialize({startOnLoad: true, theme: 'neutral', flowchart: {htmlLabels: false}});</script>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>DLTS control software: documentation</title>"
            f"<style>{CSS}</style></head><body>"
            f"<div class='cover'><div class='part'>DltsOnHallProbeSetup</div><h1>DLTS control software</h1>"
            f"<div class='sub'>Control and analysis software for deep-level transient spectroscopy on the Hall-probe "
            f"stage: Zurich Instruments MFIA and Instec mK2000B, driven from one Tkinter GUI. Guides, worked examples "
            f"and a reference page for every module.</div>"
            f"<div class='meta'>Documentation build of {date.today():%d %B %Y}</div></div>"
            f"<div class='toc'><h1>Contents</h1>{''.join(tocHtml)}</div>"
            + ''.join(parts) + script + '</body></html>')


def fetch_mermaid():
    try:
        with urllib.request.urlopen(MERMAID_URL, timeout=30) as r:
            return r.read().decode('utf-8')
    except Exception as exc:
        print(f'mermaid.js not available ({exc}); the diagram is printed as source')
        return ''


def print_pdf(page, pdfPath):
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if edge is None:
        raise RuntimeError('Microsoft Edge not found; open the --html page and print it to PDF instead.')
    if os.path.exists(pdfPath):
        os.remove(pdfPath)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'docs_print.html')
        open(src, 'w', encoding='utf-8').write(page)
        subprocess.run([edge, '--headless=new', '--disable-gpu', '--no-pdf-header-footer', '--virtual-time-budget=20000',
                        f'--print-to-pdf={os.path.abspath(pdfPath)}', 'file:///' + src.replace('\\', '/')],
                       check=True, capture_output=True, timeout=300)
        for _ in range(40):
            if os.path.exists(pdfPath) and os.path.getsize(pdfPath) > 0:
                break
            time.sleep(0.5)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Build one PDF of the documentation.')
    ap.add_argument('--out', default=os.path.join(DOCS, 'DLTS_Software_Documentation.pdf'))
    ap.add_argument('--html', help='also save the intermediate HTML page here')
    args = ap.parse_args()
    page = build_html(fetch_mermaid())
    if args.html:
        open(args.html, 'w', encoding='utf-8').write(page)
    print_pdf(page, args.out)
    print(args.out, f'{os.path.getsize(args.out) / 1e6:.1f} MB')
