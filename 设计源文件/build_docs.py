# Render the lightweight .src.txt design docs to HTML (asset-list PDF style) and print them with headless Edge.
#   # 标题        !sub / !date / !note / !box 段落        ## 01 节标题     ### 小节     #### 小小节
#   - 列表项      | 表格 | 行 |（第一行为表头）  %cols 12 30 ...（下一张表的列宽 %）    ::pb 分页
# 用法：python build_docs.py <输出文件夹> [wanfa caipu juqing]
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
table { width: 100%; border-collapse: collapse; margin: 1mm 0 3mm; font-size: 8.8pt; line-height: 1.5; text-align: left; }
th { background: var(--ink); color: #fff; font-weight: 600; text-align: left; padding: 1.8mm 2.2mm; white-space: nowrap; }
td { padding: 1.8mm 2.2mm; border-bottom: 0.5pt solid var(--rule); vertical-align: top; }
tbody tr:nth-child(odd) td { background: var(--band); }
tr { break-inside: avoid; }
td.num { white-space: nowrap; }
.tag { display: inline-block; font-size: 7.5pt; line-height: 1.35; font-weight: 600; padding: 0 1.2mm; margin: 0 0.8mm; border-radius: 1mm; vertical-align: 0.6pt; white-space: nowrap; }
.tag.new { background: #e6efe9; color: #2f6b4f; border: 0.5pt solid #9cc2ad; }
.tag.fix { background: #f7e7dd; color: #9a4a26; border: 0.5pt solid #e0b49b; }
.tag.sug { background: #eceaf4; color: #4d4a7a; border: 0.5pt solid #b9b5d6; }
b.who { font-weight: 600; }
.pb { break-after: page; }
"""

TAGS = {'新补': 'new', '修正': 'fix', '建议': 'sug'}


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
    if dialogue:
        s = re.sub(r'^([^：“”<>]{1,6})：“', r'<b class="who">\1</b>：“', s)
    return s


def render(src_path, footer, out_pdf, dialogue=False):
    lines = Path(src_path).read_text(encoding='utf-8').splitlines()
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
        elif ln.startswith('# '):
            title = ln[2:].strip(); body.append(f'<h1>{inline(title)}</h1>')
        elif ln.startswith('## '):
            t = ln[3:].strip()
            m = re.match(r'(\d{2})\s+(.*)', t)
            if m:
                body.append(f'<h2><span class="no">{m.group(1)}</span>{inline(m.group(2))}</h2>')
            else:
                body.append(f'<h2 class="part">{inline(t)}</h2>')
        elif ln.startswith('### '):
            body.append(f'<h3>{inline(ln[4:].strip())}</h3>')
        elif ln.startswith('#### '):
            body.append(f'<h4>{inline(ln[5:].strip())}</h4>')
        elif ln.startswith('!sub '):
            body.append(f'<p class="sub">{inline(ln[5:])}</p>')
        elif ln.startswith('!date '):
            body.append(f'<p class="date">{inline(ln[6:])}</p>')
        elif ln.startswith('!note '):
            body.append(f'<p class="note">{inline(ln[6:])}</p>')
        elif ln.startswith('!box '):
            paras = []
            while i < len(lines) and lines[i].startswith('!box '):
                paras.append(f'<p>{inline(lines[i][5:])}</p>'); i += 1
            body.append('<div class="box">' + ''.join(paras) + '</div>'); continue
        else:
            body.append(f'<p>{inline(ln, dialogue)}</p>')
        i += 1
    doc = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
           f'<title>{html.escape(title)}</title>\n<style>{CSS.replace("__FOOTER__", footer)}</style>\n</head>\n<body>\n'
           + '\n'.join(body) + '\n</body>\n</html>\n')
    stem = Path(src_path).name.split('.')[0]
    html_path = WORK / f'{stem}.html'
    html_path.write_text(doc, encoding='utf-8')
    tmp_pdf = WORK / f'{stem}.pdf'
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                    f'--print-to-pdf={tmp_pdf}', html_path.as_uri()], check=True, capture_output=True, timeout=180)
    shutil.copyfile(tmp_pdf, out_pdf)
    return tmp_pdf


if __name__ == '__main__':
    DOCS = {
        'wanfa':  ('汴河两岸 ｜ 玩法与数值（完整版）', '玩法与数值（完整版）.pdf', False),
        'caipu':  ('汴河两岸 ｜ 菜谱与食材（完整版）', '菜谱与食材（完整版）.pdf', False),
        'juqing': ('汴河两岸 ｜ 剧情与对话（修订版）', '剧情与对话（修订版）.pdf', True),
        'zichan': ('汴河两岸 ｜ 美术资产清单（三渲二版 · 完整版）', '资产（三渲二版）.pdf', False),
    }
    out_dir = Path(sys.argv[1])
    for key in (sys.argv[2:] or DOCS):
        footer, name, dlg = DOCS[key]
        pdf = render(HERE / f'{key}.src.txt', footer, out_dir / name, dlg)
        print('ok', key, '->', out_dir / name)
