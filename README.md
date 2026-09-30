# 《汴河两岸》

一款北宋汴京饭馆经营游戏，以及可用于博物馆的图像互动原型（课程项目）。店里的画面走三渲二：场景做成 3D 低模，用卡通着色、描边和水彩后处理渲成手绘风格；卷轴地图直接用《清明上河图》原作的公开数字图像，和博物馆模式共用。

现代厨师在自己新开的店里发现一扇门，门外是嘉祐年间的汴京。玩家在门的两边经营饭馆：采购、验货、做菜出炉、招待客人、招店小二；一道菜亲手做熟以后，灶台会自动做。时空门每天可以带一种现代食材过去；三级起可以到名流家里掌厨，五级后参加正店比拼，长期目标是成为"七十二正店之首"。

## 先看这份

| 文件 | 内容 |
| --- | --- |
| `汴河两岸_完整设计文档.pdf` | 全部设计合成一份，带目录和书签：项目概述，玩法与数值（含名流家宴、正店比拼），菜谱与食材，剧情与对话，美术资产，技术方案，经营数值核算，待定事项与文件说明 |
| `汴河两岸_菜品与家宴数据.json` | 程序数据（schema 1.3）：23 道菜、食材、调料、酒、家宴、时令、预约、点单选项、改良版、新菜反应、验货、经营数值、名流各自的条件、正店比拼和成就；菜品 ID 固定，和总文档一致，改过的键名见文件末尾的 change_log |

## 原始PDF/

原来的 PDF 都放在这里，留作对照；和总文档不一致的地方，以总文档为准。

| 文件 | 说明 |
| --- | --- |
| `玩法与数值（完整版）`、`菜谱与食材（完整版）`、`剧情与对话（修订版）`、`资产（三渲二版）` | 分册，和总文档第二至第五部分用同一份源文本生成 |
| `汴河两岸_23道菜与家宴数值(1)`、`汴河两岸_名流来访与家宴事件(1)`、`汴河两岸_正店比拼与皇帝微服事件` | GPT 整理的专题稿，内容已并入总文档；之后的改动（删羊肉、自动做菜从第二关计数等）只在总文档和 JSON 里 |
| `技术(1)` | 手机厨房技术"掌厨镜"和"试味回路"；验货已改为玩家做，内容并入总文档第六部分 |
| `大纲` | 项目提案：饭馆经营、卷轴地图、博物馆互动三部分和八周计划；并入总文档第一部分 |
| `机制(1)`、`剧情流程+对话总和`、`汴河两岸_菜单食材与经营细则`、`资产` | 早期稿，已被取代 |

## 目录

- `设计源文件/`：总文档和四份分册的源文本（`*.src.txt`）、生成脚本 `build_docs.py`、经营模拟 `economy_sim.py`。
- `WhiteModel/`：纹璃宫灯白模，包括生成脚本、`.blend` 和 `.fbx`（高模、约 3000 面、500 面定稿）、预览渲染、水彩脚本和过程图截图脚本。
- `纹璃宫灯_1_白模.png`、`纹璃宫灯_3_水彩.png`：纹璃宫灯的过程图（Blender 截图）。
- `WhiteModel/build_level1.py`、`WhiteModel/Level1/`：初始关卡（一级·1 桌）的场景白模。
- `WhiteModel/build_food.py`、`WhiteModel/Food/`：开局 3 道菜和 7 样食材、调味（面粉、时蔬、猪肉、盐、油、葱、姜）的 3D 白模，三渲二用，每件 ≤500 面。Unity 里放在 `Resources/FoodModels`，一键设置时渲成 `Resources/Food3D` 的立体图给界面用。
- `Unity/`：手机版 demo 的 Unity 工程（见下面「Unity demo」）。打包结果输出到 `Builds/`，不进仓库。

## 修改设计文档

以 `设计源文件/` 里的 `.src.txt` 为准：改源文本，再重新生成 PDF，不要直接改 PDF。

```
cd 设计源文件
python build_docs.py ..  master                                   # 总文档
python build_docs.py ../原始PDF wanfa caipu juqing zichan          # 四份分册
```

脚本把源文本排成 HTML，再用无头 Edge 打印成 PDF，所以需要 Windows、Microsoft Edge 和微软雅黑字体；总文档要排两遍来填目录页码，另需 PyMuPDF。`master.src.txt` 按顺序接入 `gaishu`（项目概述）、`wanfa`、`caipu`、`juqing`、`zichan`、`jishu`（技术方案）、`hesuan`（经营数值核算）、`daiding`（待定事项）。

源文本的写法：

- `#` 是标题，`## 01 标题` 是编号章节，`###`、`####` 是小节。
- `- ` 开头是列表；`|` 开头的行是表格，第一行为表头；`%cols` 设下一张表的列宽（百分比）。
- `!sub`、`!date`、`!note`、`!box` 分别是副标题、日期、注释和提示框；`!rev` 是改动说明，只在分册里显示。
- 总文档专用：`::toc` 目录，`::part` 部分标题，`::include 文件名 [dialogue]` 接入分册正文。
- 行内 `**粗体**`；`【新补】【修正】【建议】` 会显示成小标签。

经营数值用 `PYTHONHASHSEED=0 python 设计源文件/economy_sim.py 汴河两岸_菜品与家宴数据.json --runs 200 --prices calibrated` 复现（要固定 PYTHONHASHSEED 才能逐位对上），方法、结果和灵敏度各行的参数见总文档第七部分。

GPT 整理的三份专题稿没有源文本。9 月 26 日删学徒时，是直接在这三份 PDF 和《技术(1)》上替换了相关的句子，版式不变；之后的设计改动只进总文档和 JSON。

## 白模与三渲二

需要 Blender 5.2；水彩脚本另需 Python 3 和 Pillow、numpy。在仓库根目录运行：

```
# 生成白模：.blend、.fbx 和预览图。默认高模；--low 约 3000 面，--low500 约 500 面（定稿）
blender -b --factory-startup --python WhiteModel/build_wenli_gongdeng.py -- WhiteModel --low500 --watercolor

# 用上一步渲染的 passes 画水彩预览和物品卡
python WhiteModel/watercolor.py _500

# 在 Blender 界面里拍过程图（2560×1440）
blender --factory-startup -p 0 0 2560 1440 --no-window-focus WhiteModel/SM_WenliGongdeng_500.blend --python WhiteModel/process_shots.py -- . white,watercolor
```

三渲二那张过程图会在图像编辑器里打开老师给的参考图 `例子尝试.jpg`。参考图不在仓库里，所以上面只拍白模和水彩两张。

建模规范（圆角、全四边面、Weighted Normals、删掉看不见的面等）见总文档第五部分 03 节。

## Unity demo（初始·1桌）

用 Unity 6000.5.3f1（URP）打开 `Unity/`，运行 `Scenes/Level1`。

- 前堂：单指拖动，双指缩放，「全景」复位；「开门营业」后工人按一级①的节奏来，每天最多 12 人，平均 90 秒一组。客人入座点菜，耐心用完会催单，再过 15 秒离店。
- 点案台进入单独的平面做饭界面：选菜 → 点灶台 → 到点再点一次出炉。出炉判定、自动做计数、评价概率和经验都按总文档第二部分和 JSON 里的 `rules.service`。出炉的菜自动端给点了这道菜的桌；这一步以后改成玩家或小二端菜。
- 规则代码在 `Assets/Scripts/Core/`（不依赖 Unity，可单测）；界面和场景在 `Assets/Scripts/`。
- 字体是 Noto Sans SC 的子集（SIL OFL，见 `Assets/Resources/Fonts/`），加了新文字后用 `Unity/Tools/build_font.py` 重新生成。

改了白模以后：

```
blender -b --factory-startup --python WhiteModel/build_level1.py -- WhiteModel/Level1
copy WhiteModel\Level1\SM_Level1.fbx Unity\Assets\Art\Models\
Unity 菜单 BianHe ▸ Setup Level1        # 材质、场景、渲染管线和打包设置
```

测试与打包（菜单 BianHe 里也有）：

```
Unity -batchmode -projectPath Unity -runTests -testPlatform EditMode            # 规则单测
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildAndroid   # Builds/BianHe_Level1.apk
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildWebGL     # Builds/WebGL，手机浏览器（含 iPhone Safari）可玩
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildWindows   # Builds/Windows
Builds/Windows/BianHe.exe -shots <文件夹>                                         # 自动玩一桌客人并截图
python Unity/Tools/webgl_touch_test.py http://127.0.0.1:8765/ <文件夹>            # 模拟 iPhone 触屏测网页版
```

iOS 原生包需要 Mac 和 Xcode：在 Unity Hub 给这个版本加装 iOS Build Support，打出 Xcode 工程后在 Mac 上签名安装。iOS 的包名和系统版本已经写在 Setup 里。

## 资料来源

- 孟元老《东京梦华录》卷二、卷三、卷四、卷八，维基文库。
- 张能臣《酒名记》，见《古今图书集成·经济汇编·食货典·酒部》第二百七十三卷，维基文库。
- 蔡襄《茶录》；周密《武林旧事》卷三，维基文库（正店比拼的史料边界）。
- 故宫博物院：《张择端〈清明上河图〉卷》《北宋张择端〈清明上河图〉揭秘》。
- IIIF《Presentation API 3.0》（图像区域标注）。

## 说明

- 历史资料和游戏虚构分开标注。菜名、酒名等的出处见总文档第三部分；正店比拼、排名、皇帝微服、名流到店、名流家宴和他们的台词都是游戏虚构。游戏设定在嘉祐年间，而《东京梦华录》追记的是北宋末年的汴京，引用时作为"北宋汴京的通用参照"。
- 老师提供的参考图版权不明，参考图本身以及带参考图的对比图、截图都不放进公开仓库。
- 待定：八周原型具体交付哪些内容（见总文档第八部分）。定下来后再更新 `大纲`。
