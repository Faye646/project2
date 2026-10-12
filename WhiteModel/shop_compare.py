"""Comparison sheet for a shop level: its art beside the white model seen from the game's camera.

    python WhiteModel/shop_compare.py --level N [<shop_dir>]

Reads <shop_dir>/renders/whitemodel.png and counts.json (written by build_shop.py; <shop_dir> defaults to
WhiteModel/Shop<N>) and the level's art from the project root, and writes <shop_dir>/renders/compare.png with
Chinese captions (微软雅黑).
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = {
    1: ('初出茅庐·三桌食堂-2.png', '一级 · 初出茅庐', '大堂 3 桌'),
    2: ('餐厅增添第四张方桌-8.png', '二级 · 市井买卖', '大堂 4 桌'),
    3: ('水彩餐厅六桌布局改造-11.png', '三级 · 小有名气', '一楼 4 桌 · 二楼散座 1 桌 · 雅间 1 桌'),
    4: ('扩建双层餐厅八桌水彩图-12.png', '四级 · 声名鹊起', '一楼 4 桌 · 二楼散座 3 桌 · 雅间 1 桌'),
    5: ('楼上公共餐厅新增两桌-15.png', '五级 · 名动一方', '一楼 4 桌 · 二楼散座 6 桌 · 雅间 2 桌'),
}
FONT = 'C:/Windows/Fonts/msyh.ttc'
BG = (246, 242, 233)
INK = (74, 52, 36)


def content_box(im, alpha=False, pad=12):
    """Bounding box of what is drawn: non-transparent pixels, or pixels darker than the paper."""
    if alpha:
        box = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    else:
        g = im.convert('L').point(lambda v: 255 if v < 236 else 0)
        box = g.getbbox()
    x0, y0, x1, y1 = box
    return max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)


def main():
    args = sys.argv[1:]
    level = int(args[args.index('--level') + 1])
    rest = [a for i, a in enumerate(args) if not a.startswith('--') and args[i - 1] != '--level']
    shop = os.path.abspath(rest[0]) if rest else os.path.join(HERE, f'Shop{level}')
    art_name, title, label = ART[level]
    art = Image.open(os.path.join(ROOT, art_name)).convert('RGB')
    art = art.crop(content_box(art))
    wm = Image.open(os.path.join(shop, 'renders', 'whitemodel.png')).convert('RGBA')
    wm = wm.crop(content_box(wm, alpha=True))
    flat = Image.new('RGB', wm.size, (226, 224, 220))
    flat.paste(wm, mask=wm.getchannel('A'))
    with open(os.path.join(shop, 'renders', 'counts.json'), encoding='utf-8') as fh:
        c = json.load(fh)

    H = 900
    a = art.resize((round(art.width * H / art.height), H), Image.LANCZOS)
    w = flat.resize((round(flat.width * H / flat.height), H), Image.LANCZOS)
    if w.width > 1.45 * a.width:            # a wide model: fit both to the same width instead
        W = max(a.width, 1300)
        w = flat.resize((W, round(flat.height * W / flat.width)), Image.LANCZOS)
    gap, margin, top, foot = 40, 40, 120, 110
    Wd = margin * 2 + a.width + gap + w.width
    Hd = top + max(a.height, w.height) + 50 + foot
    sheet = Image.new('RGB', (Wd, Hd), BG)
    d = ImageDraw.Draw(sheet)
    f_title = ImageFont.truetype(FONT, 46)
    f_cap = ImageFont.truetype(FONT, 28)
    f_foot = ImageFont.truetype(FONT, 26)
    t = f'{title}　{label}'
    d.text(((Wd - d.textlength(t, font=f_title)) / 2, 28), t, fill=INK, font=f_title)
    y0 = top
    sheet.paste(a, (margin, y0 + (max(a.height, w.height) - a.height) // 2))
    sheet.paste(w, (margin + a.width + gap, y0 + (max(a.height, w.height) - w.height) // 2))
    yc = y0 + max(a.height, w.height) + 12
    cap_a = f'原画（{art_name}）'
    cap_w = '白模（游戏镜头，正交 45° / 俯角 30°）'
    d.text((margin + (a.width - d.textlength(cap_a, font=f_cap)) / 2, yc), cap_a, fill=INK, font=f_cap)
    d.text((margin + a.width + gap + (w.width - d.textlength(cap_w, font=f_cap)) / 2, yc), cap_w, fill=INK,
           font=f_cap)
    names = {'Hall': '一楼', 'Upstairs': '二楼散座', 'Yajian': '雅间'}
    per = '，'.join(f'{names.get(g, g)} {n} 桌' for g, n in c['tables_by_group'].items())
    foot_t = (f'桌 {c["tables"]}（{per}）　凳 {c["stools"]}　灶台锅 {c["woks"]}　排队点 {c["queue"]}　'
              f'三角面 {c["tris"]:,}')
    d.text(((Wd - d.textlength(foot_t, font=f_foot)) / 2, Hd - foot + 30), foot_t, fill=INK, font=f_foot)
    out = os.path.join(shop, 'renders', 'compare.png')
    sheet.save(out)
    print(out, sheet.size)


if __name__ == '__main__':
    main()
