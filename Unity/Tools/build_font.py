"""Builds Assets/Resources/Fonts/BianHeSans-{Regular,Bold}.ttf from Noto Sans SC (SIL OFL 1.1).

The variable font is pinned to weight 400 and 700, then subset to GB2312 level 1 plus every
character in the design data and the C# sources. Rerun this after adding text that uses rarer characters.
    pip install fonttools
    curl -L -o NotoSansSC.ttf "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
    python Unity/Tools/build_font.py NotoSansSC.ttf
"""
import glob
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
UNITY = os.path.dirname(HERE)
REPO = os.path.dirname(UNITY)
OUT = os.path.join(UNITY, 'Assets', 'Resources', 'Fonts')

chars = {chr(c) for c in range(0x20, 0x7f)}
for hi in list(range(0xA1, 0xAA)) + list(range(0xB0, 0xD8)):  # GB2312 symbols + level-1 hanzi
    for lo in range(0xA1, 0xFF):
        try:
            chars.add(bytes([hi, lo]).decode('gb2312'))
        except UnicodeDecodeError:
            pass
sources = glob.glob(os.path.join(REPO, '*.json'))
sources += glob.glob(os.path.join(UNITY, 'Assets', '**', '*.cs'), recursive=True)
for p in sources:
    chars |= set(open(p, encoding='utf-8').read())
chars |= set('·「」『』…—～！？，。、：；（）《》【】％')
chars = ''.join(sorted(c for c in chars if c.isprintable()))
print(len(chars), 'characters')

for weight, style in ((400, 'Regular'), (700, 'Bold')):
    font = instancer.instantiateVariableFont(TTFont(sys.argv[1]), {'wght': weight})
    opt = subset.Options()
    opt.layout_features = ['*']
    opt.name_IDs = ['*']
    opt.notdef_outline = True
    s = subset.Subsetter(opt)
    s.populate(text=chars)
    s.subset(font)
    names = {1: 'BianHe Sans', 4: f'BianHe Sans {style}', 6: f'BianHeSans-{style}', 16: 'BianHe Sans', 17: style}
    for rec in font['name'].names:  # renamed: a subset is a modified version under the OFL
        if rec.nameID in names:
            rec.string = names[rec.nameID]
    path = os.path.join(OUT, f'BianHeSans-{style}.ttf')
    font.save(path)
    print(path, os.path.getsize(path) // 1024, 'KB')
