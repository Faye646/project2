# Render the lightweight .src.txt design docs to HTML (asset-list PDF style) and print them with headless Edge.
#   # 标题        !sub / !date / !note / !box 段落        ## 01 节标题     ### 小节     #### 小小节
#   - 列表项      | 表格 | 行 |（第一行为表头）  %cols 12 30 ...（下一张表的列宽 %）    ::pb 分页
#   !rev 改动说明：单独成册时显示成提示框，合进总文档时略去（总文档另有改动记录）
# 总文档（master.src.txt）另有三条指令：
#   ::toc                      目录（两遍排版，第二遍填页码；另写 PDF 书签）
#   ::part 第一部分｜标题        部分标题，另起一页
#   ::include xxx.src.txt [dialogue]   把分册正文接进来：略去分册的 # 标题、!sub、!date、!rev；
#                              分册里不带编号的 ## 标题（如"第一部分｜剧情"）降为普通二级标题，写成"一、剧情"
# 用法：python build_docs.py <输出文件夹> [wanfa caipu juqing zichan master]
#   行内：**粗体**、【新补】【修正】【建议】标签；对白行（≤6 字说话人＋：“）自动加粗说话人
import html, re, subprocess, sys, shutil
from pathlib import Path

HERE = Path(__file__).parent
import tempfile
WORK = Path(tempfile.gettempdir()) / 'bianhe_docs'   # 中间的 HTML/PDF 放这里，不弄脏源文件夹
WORK.mkdir(exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page {
  size: A4;
  margin: 22mm 17mm 20mm 17mm;
  @top-left-corner { content: ""; background: linear-gradient(#243032 0 10mm, transparent 10mm); }
  @top-left { content: ""; background: linear-gradient(#243032 0 10mm, transparent 10mm); }
  @top-center { content: ""; background: linear-gradient(#243032 0 10mm, transparent 10mm); }
  @top-right { content: ""; background: linear-gradient(#243032 0 10mm, transparent 10mm); }
  @top-right-corner { content: ""; background: linear-gradient(#243032 0 10mm, transparent 10mm); }
  @bottom-left {
    content: "__FOOTER__";
    font-family: "Microsoft YaHei"; font-size: 8.5pt; color: #6b7572;
    vertical-align: top; padding-top: 3mm; border-top: 0.5pt solid #cfcfcf;
  }
  @bottom-right {
    content: counter(page);
    font-family: "Microsoft YaHei"; font-size: 8.5pt; color: #6b7572;
    vertical-align: top; padding-top: 3mm; border-top: 0.5pt solid #cfcfcf;
  }
}
:root { --ink: #243032; --muted: #6b7572; --band: #f4efe9; --rule: #dcd8d2; --accent: #a45a39; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; background: #fff; color: var(--ink);
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 10pt; line-height: 1.65;
  line-break: strict; text-align: justify;
}
h1 { font-size: 22pt; font-weight: 600; margin: 4mm 0 1.5mm; letter-spacing: 0.5pt; }
h1.partt { font-size: 20pt; margin: 0 0 4mm; padding-bottom: 2mm; border-bottom: 1.5pt solid var(--ink); break-before: page; break-after: avoid; }
.sub { color: var(--muted); font-size: 10.5pt; margin: 0 0 1mm; text-align: left; }
.date { color: var(--muted); font-size: 9pt; margin: 0 0 5mm; }
h2 { font-size: 14pt; font-weight: 600; margin: 8mm 0 2.5mm; break-after: avoid; }
h2 .no { color: var(--muted); font-weight: 400; margin-right: 2.5mm; }
h2.part { font-size: 16pt; margin: 10mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1pt solid var(--ink); break-after: avoid; }
h3 { font-size: 11.5pt; font-weight: 600; margin: 5mm 0 2mm; break-after: avoid; }
h4 { font-size: 10pt; font-weight: 600; color: var(--accent); margin: 3.5mm 0 1.5mm; break-after: avoid; }
p { margin: 0 0 2.2mm; }
p.note { color: var(--muted); font-size: 9pt; }
.box { background: var(--band); border-left: 2.5pt solid var(--ink); padding: 2.5mm 3.5mm; margin: 1mm 0 3mm; font-size: 9.5pt; }
.box p { margin: 0 0 1.2mm; } .box p:last-child { margin: 0; }
ul { margin: 0 0 2.5mm; padding-left: 5mm; }
li { margin: 0 0 1.2mm; }
li, p { overflow-wrap: anywhere; }   /* 长网址可以断开，前一行不被两端对齐撑开 */
table { width: 100%; border-collapse: collapse; margin: 1mm 0 3mm; font-size: 8.8pt; line-height: 1.5; text-align: left; }
th { background: var(--ink); color: #fff; font-weight: 600; text-align: left; padding: 1.8mm 2.2mm; white-space: nowrap; }
td { padding: 1.8mm 2.2mm; border-bottom: 0.5pt solid var(--rule); vertical-align: top; }
tbody tr:nth-child(odd) td { background: var(--band); }
tr { break-inside: avoid; }
td.num { white-space: nowrap; }
.nw { white-space: nowrap; }
.url { word-break: break-all; }
.tag { display: inline-block; font-size: 7.5pt; line-height: 1.35; font-weight: 600; padding: 0 1.2mm; margin: 0 0.8mm; border-radius: 1mm; vertical-align: 0.6pt; white-space: nowrap; }
.tag.new { background: #e6efe9; color: #2f6b4f; border: 0.5pt solid #9cc2ad; }
.tag.fix { background: #f7e7dd; color: #9a4a26; border: 0.5pt solid #e0b49b; }
.tag.sug { background: #eceaf4; color: #4d4a7a; border: 0.5pt solid #b9b5d6; }
b.who { font-weight: 600; }
.pb { break-after: page; }
.toc { margin: 2mm 0 0; }
.toc h2 { margin-top: 2mm; }
.toc a { color: var(--ink); text-decoration: none; }
.toc .t1, .toc .t2 { display: flex; align-items: baseline; }
.toc .t1 { font-weight: 600; font-size: 10.5pt; margin: 2.6mm 0 0.8mm; }
.toc .t2 { font-size: 9pt; margin: 0 0 0.35mm 6mm; color: var(--ink); }
.toc .dots { flex: 1; border-bottom: 0.6pt dotted #9aa3a0; margin: 0 1.5mm; transform: translateY(-1mm); }
.toc .pg { min-width: 7mm; text-align: right; color: var(--muted); }
"""

TAGS = {'新补': 'new', '修正': 'fix', '建议': 'sug'}
CN_NUM = '一二三四五六七八九十'


def curly(s):
    out, open_ = [], True
    for ch in s:
        if ch == '"':
            out.append('“' if open_ else '”'); open_ = not open_
        else:
            out.append(ch)
    return ''.join(out)


def inline(s, dialogue=False):
    s = html.escape(curly(s), quote=False)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    for word, cls in TAGS.items():
        s = s.replace(f'【{word}】', f'<span class="tag {cls}">{word}</span>')
    s = re.sub(r'([\u4e00-\u9fff][0-9]+(?:\.[0-9]+)?)', r'<span class="nw">\1</span>', s)   # 调料格数"醋2"不拆行
    s = re.sub(r'((?:https?://)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:org|com|cn|io|net|html?)(?:/[^\s，。；、）<]*)?)',
               r'<span class="url">\1</span>', s)   # 长网址任意处都能断行，前一行不被两端对齐撑开
    if dialogue:
        s = re.sub(r'^([^：“”<>]{1,6})：“', r'<b class="who">\1</b>：“', s)
    return s


class Ctx:
    """Collects headings for the master TOC and bookmarks."""
    def __init__(self):
        self.heads = []   # (level, id, plain title)
        self.n = 0

    def new_id(self):
        self.n += 1
        return f'h{self.n}'


def parse(lines, dialogue=False, included=False, ctx=None):
    """Turn .src.txt lines into a list of HTML blocks. included=True: body of a volume inside the master."""
    body, i, cols = [], 0, None
    title = ''
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            i += 1; continue
        if ln.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            out = ['<table>']
            if cols:
                out.append('<colgroup>' + ''.join(f'<col style="width:{w}%">' for w in cols) + '</colgroup>')
                cols = None
            out.append('<thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in rows[0]) + '</tr></thead><tbody>')
            for r in rows[1:]:
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>')
            out.append('</tbody></table>')
            body.append('\n'.join(out)); continue
        if ln.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append(f'<li>{inline(lines[i][2:].strip(), dialogue)}</li>'); i += 1
                while i < len(lines) and not lines[i].strip() and i + 1 < len(lines) and lines[i + 1].startswith('- '):
                    i += 1
            body.append('<ul>' + ''.join(items) + '</ul>'); continue
        if ln.startswith('%cols'):
            cols = [float(x) for x in ln.split()[1:]]
        elif ln == '::pb':
            body.append('<div class="pb"></div>')
        elif ln == '::toc' and ctx is not None:
            body.append('@@TOC@@')
        elif ln.startswith('::part ') and ctx is not None:
            t = ln[7:].strip(); hid = ctx.new_id(); ctx.heads.append((1, hid, t))
            body.append(f'<h1 class="partt" id="{hid}">{inline(t)}</h1>')
        elif ln.startswith('::include ') and ctx is not None:
            parts = ln.split()
            src = (HERE / parts[1]).read_text(encoding='utf-8').splitlines()
            body.extend(parse(src, dialogue='dialogue' in parts[2:], included=True, ctx=ctx))
        elif ln.startswith('# '):
            if not included:
                title = ln[2:].strip(); body.append(f'<h1>{inline(title)}</h1>')
        elif ln.startswith('## '):
            t = ln[3:].strip()
            m = re.match(r'(\d{2})\s+(.*)', t)
            hid = ctx.new_id() if ctx is not None else None
            idattr = f' id="{hid}"' if hid else ''
            if m:
                if ctx is not None: ctx.heads.append((2, hid, f'{m.group(1)} {m.group(2)}'))
                body.append(f'<h2{idattr}><span class="no">{m.group(1)}</span>{inline(m.group(2))}</h2>')
            elif included:
                pm = re.match(r'第([一二三四五六七八九十]+)部分｜(.*)', t)
                if pm: t = f'{pm.group(1)}、{pm.group(2)}'
                ctx.heads.append((2, hid, t))
                body.append(f'<h2{idattr}>{inline(t)}</h2>')
            else:
                if ctx is not None: ctx.heads.append((2, hid, t))
                body.append(f'<h2 class="part"{idattr}>{inline(t)}</h2>')
        elif ln.startswith('### '):
            body.append(f'<h3>{inline(ln[4:].strip())}</h3>')
        elif ln.startswith('#### '):
            body.append(f'<h4>{inline(ln[5:].strip())}</h4>')
        elif ln.startswith('!sub '):
            if not included: body.append(f'<p class="sub">{inline(ln[5:])}</p>')
        elif ln.startswith('!date '):
            if not included: body.append(f'<p class="date">{inline(ln[6:])}</p>')
        elif ln.startswith('!note '):
            body.append(f'<p class="note">{inline(ln[6:])}</p>')
        elif ln.startswith('!box ') or ln.startswith('!rev '):
            paras = []
            while i < len(lines) and (lines[i].startswith('!box ') or lines[i].startswith('!rev ')):
                if lines[i].startswith('!box ') or not included:
                    paras.append(f'<p>{inline(lines[i][5:])}</p>')
                i += 1
            if paras:
                body.append('<div class="box">' + ''.join(paras) + '</div>')
            continue
        else:
            body.append(f'<p>{inline(ln, dialogue)}</p>')
        i += 1
    if not included:
        body.insert(0, f'<!--title:{title}-->')
    return body


def page_html(body, footer):
    title = ''
    if body and body[0].startswith('<!--title:'):
        title, body = body[0][10:-3], body[1:]
    return ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            f'<title>{html.escape(title)}</title>\n<style>{CSS.replace("__FOOTER__", footer)}</style>\n</head>\n<body>\n'
            + '\n'.join(body) + '\n</body>\n</html>\n')


def print_pdf(doc_html, stem):
    html_path = WORK / f'{stem}.html'
    html_path.write_text(doc_html, encoding='utf-8')
    tmp_pdf = WORK / f'{stem}.pdf'
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                    f'--print-to-pdf={tmp_pdf}', html_path.as_uri()], check=True, capture_output=True, timeout=300)
    return tmp_pdf


def plain(t):
    return re.sub(r'【(新补|修正|建议)】', '', t).strip()


def toc_html(heads, pages):
    out = ['<div class="toc"><h2>目录</h2>']
    for lvl, hid, t in heads:
        pg = str(pages.get(hid, '')) if pages else '00'
        out.append(f'<div class="t{lvl}"><a href="#{hid}">{inline(plain(t))}</a><span class="dots"></span>'
                   f'<a class="pg" href="#{hid}">{pg}</a></div>')
    out.append('</div><div class="pb"></div>')
    return '\n'.join(out)


def render(src_path, footer, out_pdf, dialogue=False):
    lines = Path(src_path).read_text(encoding='utf-8').splitlines()
    stem = Path(src_path).name.split('.')[0]
    if stem != 'master':
        pdf = print_pdf(page_html(parse(lines, dialogue), footer), stem)
        shutil.copyfile(pdf, out_pdf)
        return pdf
    # master: pass 1 finds where each heading lands (Edge keeps #anchors as PDF links), pass 2 prints page numbers
    import fitz
    ctx = Ctx()
    body = parse(lines, dialogue, ctx=ctx)
    pages = {}
    for rnd in (1, 2):
        b = [toc_html(ctx.heads, pages if rnd == 2 else None) if x == '@@TOC@@' else x for x in body]
        pdf = print_pdf(page_html(b, footer), stem)
        d = fitz.open(pdf)
        found = {}
        for pno in range(d.page_count):
            for ln in d[pno].get_links():
                name = ln.get('nameddest') or ''
                if name in {h[1] for h in ctx.heads} and 'page' in ln:
                    found[name] = ln['page'] + 1
        if rnd == 2 and found != pages:
            raise RuntimeError('目录页码在第二遍排版后变了')
        pages = found
        d.close()
    missing = [t for _, hid, t in ctx.heads if hid not in pages]
    if missing:
        raise RuntimeError(f'这些标题没找到页码：{missing}')
    d = fitz.open(pdf)
    d.set_toc([[lvl, plain(t), pages[hid]] for lvl, hid, t in ctx.heads])
    d.save(out_pdf, garbage=3, deflate=True)
    d.close()
    return out_pdf


if __name__ == '__main__':
    DOCS = {
        'wanfa':  ('汴河两岸 ｜ 玩法与数值（完整版）', '玩法与数值（完整版）.pdf', False),
        'caipu':  ('汴河两岸 ｜ 菜谱与食材（完整版）', '菜谱与食材（完整版）.pdf', False),
        'juqing': ('汴河两岸 ｜ 剧情与对话（修订版）', '剧情与对话（修订版）.pdf', True),
        'zichan': ('汴河两岸 ｜ 美术资产清单（三渲二版 · 完整版）', '资产（三渲二版）.pdf', False),
        'master': ('汴河两岸 ｜ 完整设计文档', '汴河两岸_完整设计文档.pdf', False),
    }
    out_dir = Path(sys.argv[1])
    for key in (sys.argv[2:] or DOCS):
        footer, name, dlg = DOCS[key]
        render(HERE / f'{key}.src.txt', footer, out_dir / name, dlg)
        print('ok', key, '->', out_dir / name)
