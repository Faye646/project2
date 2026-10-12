# 《汴河两岸》

一款北宋汴京饭馆经营游戏，以及可用于博物馆的图像互动原型（课程项目）。店里的画面走三渲二：场景做成 3D 低模，用卡通着色、描边和水彩后处理渲成手绘风格；卷轴地图直接用《清明上河图》原作的公开数字图像，和博物馆模式共用。

现代厨师在自己新开的店里发现一扇门，门外是嘉祐年间的汴京。玩家在门的两边经营饭馆：采购、验货、做菜出炉、招待客人、招店小二；一道菜亲手做熟以后，灶台会自动做。时空门每天可以带一种现代食材过去；三级起可以到名流家里掌厨，五级后参加正店比拼，长期目标是成为"七十二正店之首"。

## 先看这份

| 文件 | 内容 |
| --- | --- |
| `汴河两岸_完整设计文档.pdf` | 全部设计合成一份，带目录和书签：项目概述，玩法与数值（含名流家宴、正店比拼），菜谱与食材，剧情与对话，美术资产，技术方案，经营数值核算，待定事项与文件说明 |
| `汴河两岸_菜品与家宴数据.json` | 程序数据（schema 1.3）：23 道菜、食材、调料、酒、家宴、时令、预约、点单选项、改良版、新菜反应、验货、经营数值、名流各自的条件、正店比拼和成就；菜品 ID 固定，和总文档一致，改过的键名见文件末尾的 change_log |
| `Unity/` | 可以玩的手机版 demo：开店、做菜、端菜、结账，店面从初始一路升到五级，桌子一张张买、扩建二楼与雅间，见「Unity demo」 |
| `WhiteModel/StyleTest/` | 进度图：`游戏实拍_截图.png`（游戏里实拍）、`全部菜品原料调料_总图.png`（全部菜、原料和调料，原图对照游戏里的样子）、`添置桌椅与扩建_游戏实拍.png`（买桌子和扩建二楼的过程）、`灶台四块_游戏实拍.png`（做饭界面的四口锅）、`采购验货与自动做菜_游戏实拍.png`（集市采购、验货、库存和自动做菜），以及各次修改的描线图和前后对比 |

## 目录

| 路径 | 内容 |
| --- | --- |
| `设计源文件/` | 总文档和四份分册的源文本（`*.src.txt`）、生成脚本 `build_docs.py`、经营模拟 `economy_sim.py` |
| `原始PDF/` | 原来的 PDF，留作对照（见下） |
| `新建文件夹/` | 菜、食材、调料的原图，3D 模型照着它们一比一还原 |
| `WhiteModel/` | Blender 脚本和它们导出的模型：店面场景（`build_level1.py`、`build_shop.py`），菜、食材和调料（`build_food.py`、`food_models/`），做饭界面的 3D 案台（`build_cook_view.py`），纹璃宫灯（`build_wenli_gongdeng.py`），画风样张（`style_test.py`） |
| `Unity/` | 手机版 demo 的 Unity 工程（URP）；打包结果输出到 `Builds/`，不进仓库 |
| `纹璃宫灯_1_白模.png`、`纹璃宫灯_3_水彩.png` | 纹璃宫灯的过程图（Blender 截图） |

## 原始PDF/

原来的 PDF 都放在这里，留作对照；和总文档不一致的地方，以总文档为准。

| 文件 | 说明 |
| --- | --- |
| `玩法与数值（完整版）`、`菜谱与食材（完整版）`、`剧情与对话（修订版）`、`资产（三渲二版）` | 分册，和总文档第二至第五部分用同一份源文本生成 |
| `汴河两岸_23道菜与家宴数值(1)`、`汴河两岸_名流来访与家宴事件(1)`、`汴河两岸_正店比拼与皇帝微服事件` | GPT 整理的专题稿，内容已并入总文档；之后的改动（删羊肉、自动做菜从第二关计数等）只在总文档和 JSON 里 |
| `技术(1)` | 手机厨房技术"掌厨镜"和"试味回路"；验货已改为玩家做，内容并入总文档第六部分 |
| `大纲` | 项目提案：饭馆经营、卷轴地图、博物馆互动三部分和八周计划；并入总文档第一部分 |
| `机制(1)`、`剧情流程+对话总和`、`汴河两岸_菜单食材与经营细则`、`资产` | 早期稿，已被取代 |

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

## Unity demo

用 Unity 6000.5.3f1（URP）打开 `Unity/`，运行 `Scenes/Level1`。改了模型或颜色以后，跑一次菜单 BianHe ▸ Setup Level1：重建材质、场景、渲染管线和打包设置，并重新烘焙界面用的菜品立体图。

### 怎么玩

- 前堂：单指拖动，双指缩放，「全景」复位。「开门营业」后客人按当前声望阶段的节奏来，有空桌就入座点菜，营业 6 分钟后打烊结算。每张桌子上方有一个气泡（等菜几份和剩下的耐心、催单、用餐中、结账），门口排队的客人另有一个气泡。耐心用完会催单，再过 15 秒离店。
- 采购（开门前，总文档第二部分 06「采购、验货与库存」，数字在 JSON 的 `rules.procurement`、`rules.service.bargain` 和各食材的字段里）：
  - 开门前点右上角「采购」去集市。左边一列是摊位：面米铺、调料（也是面米铺卖的）、肉铺、菜贩，经验够了再多出禽蛋铺、鱼行、豆腐坊、酱菜干货铺。
  - 每样东西一张卡：库存还有几份、能做哪几道菜，普通和优质两档的价钱（优质贵一半、坏料少），点「+」「+10」选份数。同一样主料一次买 10 份打九折，20 份以上八折，但压在下面的容易坏，坏料多五个百分点。调料只有一档，不打折，也不占库存。
  - 砍价：每个摊位每天能砍一次，三种说法——“让一点吧”九五折九成能成，“再便宜些”九折六成，“就这个价”八折三成。砍成了，这家当天的东西都按砍后的价；砍不下来就原价，当天不再讲价。和整筐折扣相乘，最低原价七成。
  - 最下面一行是这一趟买了什么、共多少钱；钱不够或者库存放不下（主料上限：一级 60 份、二级 100、三级 180、四级 240、五级 320）时不能买下。
- 验货：买下以后马上自动验货，坏料挑出来丢掉，页面列出每样挑出几份、入库几份。约二十分之一的坏料会漏掉，出锅时才发现，那盘作废、食材全损。总文档里自动验货是 3 级小二的本事，没有小二时要玩家自己点出坏料；游戏里还没有小二，也没有坏料的外观美术，所以先从开局就自动验。
- 库存：做菜开火时一次扣掉这道菜的全部主料和调料，缺一样就开不了火。主料全用优质时，这盘菜的好评加 10 个百分点（库存里优质够，就先用优质）。客人只点库存还做得出来的菜，先算上已经点了还没做的；一道都做不出来时，进门的客人直接走。打烊时剩下的每份各自抽一次过夜损耗：蔬菜、水产 30%，肉禽蛋和豆腐 20%，面米干货和调料不坏。打烊结算列出当天买了多少、丢了多少坏料、用掉多少、过夜坏了多少，和剩下的库存。
- 自动做菜（总文档第二部分 02）：从第二天起计数，一道菜亲手做出完美满 3 次（中等菜 8 次）就开启自动做。开启以后，这道菜的单自己放到空闲的锅上做（最多同时占两口锅，玩家正在放料的锅不碰），也照样扣库存，到点自己出锅（完美），有空托盘就自己装盘。锅前的小牌子写「自动·胡饼」，点它只会提示它在自动做。
- 做菜：点「案台」进入做饭界面（3D 案台场景）。食材板只摆选中的那道菜要的东西：主料在后排，调料在前排，名字后面是库存份数，用完的变红、东西不见。
  1. 选菜，点亮起来的食材和调味，生原料一样样掉进锅里。
  2. 放齐就开火，原料在锅里上下翻炒，在空中翻面。
  3. 指针在金色里时点「出锅」，锅里的原料变成成品。
  4. 点「装盘」，或者打开「自动装盘」（出锅一秒多后自己装），菜飞到放置区的空托盘上。
  5. 点托盘，把菜端给客人。
- 灶台分成四块，一块一口锅、一个灶口：
  - 一级①只开第一块，每升一级（一级②、一级③、二级）多开一块，二级起四口锅全开。没开的那块盖着木锅盖，灶口不烧火，下面写着哪一级开。
  - 每口锅各做各的菜。点一口锅就选中它，火候表、「出锅」「装盘」都对选中的那口；再点选中的锅，等于点按钮。指针正在金色里的锅、已经出锅等装盘的锅，不用先选中，点一下就出锅或装盘。
  - 从食材板点的东西放进选中的锅；那口锅正忙时，自动放进下一口空锅。
  - 每口锅前沿有一张小牌子：空着、放料几样、做的菜和小火候条（指针进金色时牌子变金）、糊了、出锅等装盘，出锅那一刻显示完美、没熟等结果。
  - 升级当天的打烊结算会写「明天灶台多开一口锅」，第二天开门时也会提示。
- 出锅判定、自动做的计数、评价概率和经验都按总文档第二部分和 JSON 里的 `rules.service`。
- 店面随声望升级：打烊结算时升了级，第二天开门就是新店面。
- 添置桌椅（总文档第二部分 04「桌椅、灶台与扩建」，价格在 JSON 的 `rules.economy.tables` 和 `expansion`）：
  - 开张只有 1 张桌。升级不送桌子，只放开这一级最多能有几张，其余要一张张买。
  - 购买顺序和经营模拟一样：先买一楼第 2–4 张；一楼 4 张买齐后，三级起可以扩建二楼与雅间；扩建开张后再买二楼第 7–12 张，第 12 张是雅间二。
  - 下一张能买的桌子摆在它将来的位置上，画成半透明的蓝色草图，头上标着价钱，点它或点右上角「添置」都能打开添置页。
  - 添置页列出下一样能买的东西、价钱，以及现在为什么还不能买（等级不够或钱不够），下面按一楼、二楼、雅间列出全部 12 张桌的状态。
  - 买下的桌子带着凳子弹出来，营业中买的马上能坐客人。
  - 扩建时镜头移到二楼，看着它一块块修起来：先修底层和楼梯，再铺楼板、立墙和栏杆，最后摆上第 5 张桌和雅间一的桌子。修好后头上挂「二楼明天开张」，第二天客人才能上楼。
  - 打烊结算会列出当天添置了什么。升级后能买新东西时，结算页和第二天开门时都会提示。门口客人因为没空桌离开时，如果有桌子能买，也会提示。

| 声望阶段 | 累计经验 | 店面 | 最多几张桌 | 这一级能添置的 | 每天客人上限 |
| --- | --- | --- | --- | --- | --- |
| 一级① 初出茅庐 | 0 | 初始·1 桌 | 1 | — | 12 |
| 一级② | 60 | 一级店面 | 2 | 第 2 张桌 60 文 | 18 |
| 一级③ | 150 | 一级店面 | 3 | 第 3 张桌 120 文 | 24 |
| 二级 市井买卖 | 300 | 二级店面 | 4 | 第 4 张桌 250 文 | 36 |
| 三级 小有名气 | 650 | 三级店面（有二楼和雅间） | 6 | 扩建二楼与雅间 700 文（含第 5、6 张桌，第二天开张） | 54 |
| 四级 声名鹊起 | 1200 | 四级店面 | 8 | 第 7、8 张桌各 250 文 | 72 |
| 五级 名动一方 | 2100 | 五级店面 | 12 | 第 9–12 张桌各 350 文（第 12 张是雅间二） | 96 |

总文档同一节里还有灶台的价格和每级上限（一级③ 4 口、五级 12 口），游戏里没有用：灶台改成了四块，随升级开，不用买。

### 画面

- 画风（老师认可的 C 版）：3D 模型 + 从手绘图截取的贴图 + 水彩式分层光影，着色器 `Assets/Art/Shaders/WatercolorLit.shader`（Blender 端是 `WhiteModel/wc_materials.py`）。可乐瓶是透明玻璃，用 `WatercolorGlass.shader`。
- 影子是卡通投影：只落在地面、凳面、桌面、灶台这类朝上的面上，平涂一种偏冷的深色，边缘干净。投影用的太阳在高处（仰角 72°），和画面受光在同一侧，影子落在东西正下方、稍偏后。画面的明暗方向另由太阳上的 `ShadeLight` 交给着色器，不跟着太阳走。前堂摄像机的近、远裁剪面随缩放收紧（`CameraRig`），阴影贴图只盖住看得见的范围，边缘更清楚。纸片人客人脚下是一块圆形的影子。
- 摆放不穿模（`Assets/Scripts/FoodFit.cs`；食物模型按可读网格导入，运行时量顶点）：
  - 锅里：生原料按大小在锅底排一圈，靠着锅的弧度斜放；翻面时跳得够高，转起来碰不到锅和旁边的原料。出锅后的成品缩进锅内，再按锅底的弧度弯曲贴合。
  - 放置区：菜放大或缩小到正好填满自己的格子，不碰格子边。
  - 案板：食材前后两排，各占一格。
  - 餐桌：端上桌的菜转向镜头（菜是照原图的视角建的，从侧面看会像被拉变形），在点菜的客人面前一字排开，互相不重叠，也不碰茶杯。

### 代码

| 文件（`Unity/Assets/`） | 做什么 |
| --- | --- |
| `Scripts/Core/` | 规则，不依赖 Unity，可单测：营业日 `BusinessDay`、客人与评价 `Service`、灶台与出锅判定 `Stove`、`CookRules`，自动做的计数 `CookBook`，买桌子和扩建 `Premises`，库存、采购价钱、砍价、验货和过夜损耗 `Pantry`，读设计数据 `GameData` |
| `Scripts/GameFlow.cs` | 整体流程：前堂和做饭界面的切换、营业按钮和结算、按声望换店面、添置页、自动截图和演示模式 |
| `Scripts/GameSession.cs` | 跨界面的状态：钱、经验、买下的桌子、库存和当天的集市、灶台、锅里的菜、放置区、当天的客人；自动做菜也在这里跑 |
| `Scripts/MarketScreen.cs` | 集市采购页：摊位、每样东西的卡片、砍价、这一趟的单子、到货验货 |
| `Scripts/CookingScreen.cs` | 做饭界面：3D 案台、选菜、食材板、四口锅（选锅、各自翻炒、锅前的小牌子）、出锅、装盘、火候表 |
| `Scripts/GuestViews.cs` | 前堂的纸片人客人、每张桌子的气泡、端上桌的菜 |
| `Scripts/ShopFloor.cs` | 店里的桌椅按买了多少摆：没买的收起来，下一张画成草图并标价，买下时弹出来，扩建时二楼一块块修起来，挂「明天开张」 |
| `Scripts/FoodFit.cs` | 量食物模型，把它放进锅、格子和桌面而不穿模 |
| `Scripts/CameraRig.cs` | 前堂摄像机：拖动、缩放、裁剪面、描边粗细 |
| `Scripts/ShadeLight.cs` | 把画面受光的方向和投影用的太阳分开 |
| `Scripts/CookStation.cs` | 前堂里可以点的案台和它头上的提示 |
| `Scripts/UIKit.cs`、`Scripts/JObjectLite.cs` | 界面小工具；读 `cook_set.json` |
| `Editor/ProjectSetup.cs` | 一键设置：材质、场景、渲染管线、菜品立体图、打包 |
| `Editor/Level1ModelPostprocessor.cs` | 导入模型：给描边用的平滑法线，店面和食物的网格保持可读 |
| `Art/Shaders/` | `WatercolorLit`（水彩光影、卡通投影、食物的光泽和细节纹理）、`WatercolorGlass`（透明玻璃）、`PaintedCard`（案台场景里的手绘卡片） |
| `Resources/Shaders/Ghost.shader` | 待买的桌子和二楼的草图：半透明，带蓝色描边和细斜线，会轻轻呼吸。放在 Resources 里，打包时才会带上 |

字体是 Noto Sans SC 的子集（SIL OFL，见 `Assets/Resources/Fonts/`），加了新文字后用 `Unity/Tools/build_font.py` 重新生成。

### 测试、截图与打包

菜单 BianHe 里也有这些：

```
Unity -batchmode -projectPath Unity -runTests -testPlatform EditMode            # 规则单测
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.SetupAll        # 同菜单 Setup Level1
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildAndroid    # Builds/BianHe_Level1.apk
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildWebGL      # Builds/WebGL，手机浏览器（含 iPhone Safari）可玩
Unity -batchmode -quit -projectPath Unity -executeMethod BianHe.EditorTools.ProjectSetup.BuildWindows    # Builds/Windows
Builds/Windows/BianHe.exe -shots <文件夹>                       # 自动玩一桌客人并截图（截图、录像这几种模式开局先把库存补满，每样 30 份）
Builds/Windows/BianHe.exe -stage 2 -shopshot <文件夹>           # 从某个声望阶段开始（1_1、1_2、1_3、2…5，这一级能有的桌子都当作已经买了），给那一级的店面坐满客人拍照
Builds/Windows/BianHe.exe -stage 3 -own 4 -cash 1000 -buyshots <文件夹>   # 只有前 4 张桌、1000 文：拍下一样东西从草图、添置页到买下（扩建还拍修建过程、第二天开张和楼上坐客）
Builds/Windows/BianHe.exe -wok <文件夹> D08,D07                 # 直接做这几道菜，拍锅里翻炒和出锅的特写
Builds/Windows/BianHe.exe -stage 1_3 -stoveshots <文件夹>       # 拍这一级的灶台：开了几口锅，每口锅各做一道菜，第一口出锅
Builds/Windows/BianHe.exe -stage 1_2 -marketshots <文件夹>      # 拍一趟采购：选东西、砍价、到货验货、食材板上的库存、结算里的食材
Builds/Windows/BianHe.exe -stage 1_3 -autoshots <文件夹>        # 拍自动做菜：开着的菜都算做熟了，坐满客人后锅自己做、自己装盘
python Unity/Tools/record_video.py <视频.mp4>                  # 自动演示并录屏（-video：开店、做菜、上桌、锅里和放置区特写），约两分钟
python Unity/Tools/webgl_touch_test.py http://127.0.0.1:8765/ <文件夹>   # 模拟 iPhone 触屏测网页版
```

iOS 原生包需要 Mac 和 Xcode：在 Unity Hub 给这个版本加装 iOS Build Support，打出 Xcode 工程后在 Mac 上签名安装。iOS 的包名和系统版本已经写在 Setup 里。

## 店面白模（初始到五级）

前堂和后厨的白模都是 Blender 脚本照布局图搭的。墙、栏杆、台阶、灯笼、门帘、方桌、方凳这些共用零件，以及统计、导出和渲染，都在 `WhiteModel/level_kit.py`。建模规范（圆角、全四边面、Weighted Normals、删掉看不见的面等）见总文档第五部分 03 节。

| 等级 | 布局图 | 桌子 | 脚本和白模 | 三角面 |
| --- | --- | --- | --- | --- |
| 初始·1 桌 | 老师给的 `初始1桌布局.jpg` | 1 | `build_level1.py` → `WhiteModel/Level1/SM_Level1.fbx` | 3.7 万 |
| 一级 | `初出茅庐·三桌食堂-2.png` | 大堂 3 | `build_shop.py --level 1` → `WhiteModel/Shop1/SM_Shop1.fbx` | 5.5 万 |
| 二级 | `餐厅增添第四张方桌-8.png` | 大堂 4 | `--level 2` → `Shop2/SM_Shop2.fbx` | 6.0 万 |
| 三级 | `水彩餐厅六桌布局改造-11.png` | 一楼 4、二楼 1、雅间 1 | `--level 3` → `Shop3/SM_Shop3.fbx` | 9.6 万 |
| 四级 | `扩建双层餐厅八桌水彩图-12.png` | 一楼 4、二楼 3、雅间 1 | `--level 4` → `Shop4/SM_Shop4.fbx` | 10.0 万 |
| 五级 | `楼上公共餐厅新增两桌-15.png` | 一楼 4、二楼 6、雅间 2 | `--level 5` → `Shop5/SM_Shop5.fbx` | 11.8 万 |

- 同一级的其他几张布局图是早期版本，桌数和标题对不上，没有用。
- 游戏认这些名字：`K_AnTai`（案台，点它进做饭界面）、`K_ZaoTai`（灶台）、`D_Table_<n>` 和每张桌的四个凳子 `D_Stool_<n>_<k>`（初始关卡是 `D_Stool_1…4`）、`Spot_Queue_1…4`（门外排队的位置）；分组是 `Kitchen`、`Corridor`、`Hall`、`Upstairs`、`Yajian`。
- 桌子按设计里买桌子的顺序编号：1–4 在一楼，5 和 7–11 在二楼，6 是雅间一，12 是雅间二。游戏里只摆出买下的桌子；扩建以前，`Upstairs`、`Yajian` 两组和上楼的 `D_Stairs`（五级还有 `D_Walkway`）都收起来，扩建时再一块块修起来。
- 二楼照布局图的剖面画法，放在一楼大堂的后上方，从游戏视角两层的桌子都看得见。
- 桌子都是 1 米的方桌配 4 个凳子（布局图里画成长桌的也一样，游戏里一桌坐 4 人），桌凳之间至少留 0.5 米过道。花草、盆栽和树都没放，等花草的美术。
- 和布局图不一样的地方：
  - 二级的厨房和大堂在图里只挨着一个角，没有路走，加了一条 2 米的走廊，大堂比图里靠前一点。
  - 四级的楼梯底端往右挪了约 2 米：照图里的位置，那段楼梯太陡。
  - 五级灶台后面的架子简化成一排矮柜，雅间正面用实墙，没用格栅，都是为了控制面数。

改了店面以后：

```
blender -b --factory-startup --python WhiteModel/build_level1.py -- WhiteModel/Level1
blender -b --factory-startup --python WhiteModel/build_shop.py -- --level 2      # 1–5 = 一级…五级，写到 WhiteModel/Shop<n>/
python WhiteModel/shop_compare.py --level 2                                       # 布局图和白模并排：WhiteModel/Shop<n>/renders/compare.png
blender -b WhiteModel/Shop2/SM_Shop2.blend --python WhiteModel/check_shop.py      # 穿模、悬空检查
copy WhiteModel\Level1\SM_Level1.fbx Unity\Assets\Art\Models\
copy WhiteModel\Shop2\SM_Shop2.fbx Unity\Assets\Art\Models\
Unity 菜单 BianHe ▸ Setup Level1        # 材质、场景、渲染管线和打包设置
```

## 菜、食材和调料

### 模型

- 设计数据里全部 23 道菜，另有酸菜鱼辣味版 `D20_spicy`（松鼠鳜鱼淀粉脆皮版的原图和原版一样，共用 `D18`）。每道菜有装盘和锅里（`_wok`）两个版本。
- 除 6 种酒以外的全部 38 样食材、调料，另有一个通用的青瓷酒壶 `wine`（按 `酒_待定.png` 做，等每种酒有了图再分开）。
- 一共 87 个模型（`SM_<id>`）。每件都按原图一比一还原形状和摆放（从原图的视角：正前方、俯角 35°），全部圆角、平滑，不留尖角和棱面，每件 ≤8000 个三角面。
- 建模代码在 `WhiteModel/food_models/`：`core.py` 是共用部分（调色板与光泽、网格构建、碗盘、酱汁、配菜、鱼身、麻袋竹筐、对位工具），其余每个文件一组：`bowls`、`plates`、`stirfry`（菜），`meat_fish`、`produce`、`sacks`、`jars`（食材、调料），`wok_raw`（锅里的生原料）。`WhiteModel/build_food.py` 负责构建、导出和预览，输出到 `WhiteModel/Food/`。
- Unity 里放在 `Assets/Resources/FoodModels`；一键设置时套上水彩材质，并从原图的视角渲成 `Resources/Food3D` 的立体图给界面用。

### 照原图描线（勾勒）

大部分菜和食材的形状是从原图上描出来的：每个描线脚本在 `新建文件夹/` 的原图上把每一块描出轮廓、分出颜色，按原图的视角反投成 3D，结果写进 `food_models/traced_<id>.json`（颜色分区另存 `_paint.npz` 或 `_paint.png`），建模代码读它来建。加 `--sheet <图.png>` 会画一张描线图，例如 `WhiteModel/StyleTest/番茄炒蛋_鸡蛋勾勒.png`、`酒蟹_勾勒.png`、`煎鱼饭_勾勒.png`、`松鼠鳜鱼_勾勒.png`、`两熟紫苏鱼_勾勒.png`、`酸菜鱼_勾勒.png`。

| 脚本（`WhiteModel/`） | 描的是 |
| --- | --- |
| `trace_d01.py`、`d03`、`d04`、`d05`、`d06`、`d07`、`d08` | 胡饼、馄饨、瓜齑萝卜、水晶脍、番茄炒蛋、宫保鸡丁、可乐鸡翅 |
| `trace_d10.py`、`d12`、`d13`、`d14`、`d15`、`d16`、`d18`、`d19` | 煎鱼饭、两熟紫苏鱼、土豆炖肉、玉板鲊、荔枝腰子、文思豆腐、松鼠鳜鱼、北京烤鸭 |
| `trace_d20.py`（加 `--spicy` 是辣味版）、`trace_d23.py` | 酸菜鱼、酒蟹 |
| `trace_noodles.py D02`、`D09`、`D11` | 菜面、插肉面、冷淘 |
| `trace_duck.py`、`wing`、`greens`、`perilla`、`radish`、`potato`、`ginger`、`scallion`、`garlic` | 鸭、鸡翅、时蔬、紫苏、萝卜、土豆、姜、葱、蒜 |
| `trace_rice_prep.py`、`pickle_base`、`seafood`、`pancake`、`sauerkraut` | 米料备料、盐渍辅料包、干贝海味包、薄饼备料、酸菜 |
| `trace_common.py`、`trace_kit_plates.py`、`trace_heap.py`、`trace_veg.py`、`trace_packs.py` | 共用工具：原图的相机、分块、按轮廓建面、颜色分区，盘装菜、堆起来的菜、蔬菜和包装食材各自的做法 |

没有列出的（麻婆豆腐、佛跳墙、剁椒鱼头和其余食材、调料）是照原图对位建的（`art_match.py`）。

### 颜色和质感

- 食物另加光泽和更浓的颜色：每种颜色的强弱在 `core.py` 的 `GLOSS`、`VIVID` 里调，反光点的大小在 `WatercolorLit.shader` 里调。
- 细节纹理和凹凸：`WhiteModel/food_textures.py` 生成 32 张无缝贴图（`Unity/Assets/Art/Textures/food_*.png`），有猪肉的肥瘦花纹、肉的肌理、禽皮和猪皮的毛孔、腰子的斑驳、炒蛋的褶皱、番茄籽、鱼鳞、煎鱼皮、蟹壳的斑驳、剁椒的颗粒、油炸面衣、胡饼的焦斑和气孔、可乐气泡、米粒、面条、叶脉、竹编、木纹、布纹、纸褶、陶土、土豆皮、姜皮、蒜皮等。哪种颜色用哪张、多密、多深在 `core.py` 的 `DETAIL` 里调（模型没有 UV，着色器在物体空间里三向投射）。
- 渐变和晕染画在顶点颜色上（`Part.tint`，接受晕染的颜色列在 `core.py` 的 `VTINT`）：鱼头顶的深灰、蟹腿节边的棕黄、鳜鱼的斑点、煎鱼背上的焦色、紫苏叶边的绿。
- 可乐瓶是透明玻璃：哪些颜色是玻璃、多透、高光多强列在 `core.py` 的 `GLASS`。米粒这类小颗粒的描边细一些，列在 `OUTLINE`。

### 锅里的生原料

`WhiteModel/food_models/wok_raw.py` 把 28 样主料做成实心的生原料块：面团、米饭、肉块、鸡丁、鸡蛋、鸡翅、整条鱼、整只蟹、番茄块、辣椒、菜叶等，按真实尺寸建，从哪面看都是真的，在锅里翻面不会像纸片。`WhiteModel/build_raw.py` 生成 `RAW_<id>.fbx`，每样进锅几块、多大写在 `raw_pieces.json`。游戏里小块放大 2.6 倍，整鱼、整蟹放大 1.3 倍。

### 检查和对照

- `check_backfaces.py`：Unity 剔除背面，翻面和漏缝都要在 0.5% 以下。
- `check_vessels.py`：菜不能从盘碗的外壁、底下穿出来。
- `art_views.py` 和 `art_match.py`：从原图的视角渲染，再和原图对位（重合度 IoU、红线轮廓、厘米网格）。
- `preview_wc.py`：不开 Unity，按水彩着色器的算法（顶点晕染、细节纹理和凹凸、四档光影、反光、描边）渲出接近游戏图标的预览。
- 对照图：`WhiteModel/Food/新菜品对照.png`、`新食材对照.png`（原图对照模型），`WhiteModel/StyleTest/全部菜品原料调料_总图.png`（原图对照游戏里的样子），以及各次修改的前后对比（`StyleTest/*_前后对比.png`、`*_重做*.png`）。

改了菜、食材或调料的模型以后（`--only` 只重建列出的几样，不加就全部重建）：

```
python WhiteModel/trace_d06.py --sheet WhiteModel/StyleTest/番茄炒蛋_鸡蛋勾勒.png   # 只在原图或描法变了时重描；番茄炒蛋约 4 分钟，其余几秒到半分钟
python WhiteModel/trace_d20.py --spicy --sheet WhiteModel/StyleTest/酸菜鱼辣味版_勾勒.png   # 酸菜鱼辣味版；其余描线脚本的用法写在各自开头
blender -b --factory-startup --python WhiteModel/build_food.py -- WhiteModel/Food --only rice,egg
blender -b --factory-startup --python WhiteModel/preview_wc.py -- WhiteModel/Food previews rice,egg   # 不开 Unity 的图标预览（接近水彩着色器）
blender -b --factory-startup --python WhiteModel/build_raw.py -- WhiteModel/Food   # 锅里的生原料 RAW_<id>.fbx 和 raw_pieces.json（--only id,id 只重建几样）
blender -b --factory-startup --python WhiteModel/check_backfaces.py -- WhiteModel/Food rice,egg
blender -b --factory-startup --python WhiteModel/check_vessels.py -- WhiteModel/Food
blender -b --factory-startup --python WhiteModel/art_views.py -- WhiteModel/Food views rice "0,35"   # 从原图的视角渲染
python WhiteModel/art_match.py 新建文件夹/米.png views rice match_rice.png   # 和原图对位
copy WhiteModel\Food\SM_rice.fbx Unity\Assets\Resources\FoodModels\
copy WhiteModel\Food\RAW_rice.fbx Unity\Assets\Resources\FoodModels\
copy WhiteModel\Food\raw_pieces.json Unity\Assets\Resources\
copy WhiteModel\Food\palette_food.json Unity\Assets\Art\
blender -b --factory-startup --python WhiteModel/build_cook_view.py -- --export WhiteModel/CookView/export
copy WhiteModel\CookView\export\cook_set.json Unity\Assets\Resources\   # 新颜色的水彩参数在这里，漏了就还是旧的卡通材质
copy WhiteModel\CookView\export\CookSet.fbx Unity\Assets\Art\Models\    # 做饭界面的 3D 案台：三个托盘、食材板、四块灶台（每块一口锅、一个灶口、一个锅盖）
Unity 菜单 BianHe ▸ Setup Level1        # 生成材质，重新烘焙 Food3D 图标
```

## 纹璃宫灯（白模与三渲二）

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

## 资料来源

- 孟元老《东京梦华录》卷二、卷三、卷四、卷八，维基文库。
- 张能臣《酒名记》，见《古今图书集成·经济汇编·食货典·酒部》第二百七十三卷，维基文库。
- 蔡襄《茶录》；周密《武林旧事》卷三，维基文库（正店比拼的史料边界）。
- 故宫博物院：《张择端〈清明上河图〉卷》《北宋张择端〈清明上河图〉揭秘》。
- IIIF《Presentation API 3.0》（图像区域标注）。

## 说明

- 历史资料和游戏虚构分开标注。菜名、酒名等的出处见总文档第三部分；正店比拼、排名、皇帝微服、名流到店、名流家宴和他们的台词都是游戏虚构。游戏设定在嘉祐年间，而《东京梦华录》追记的是北宋末年的汴京，引用时作为"北宋汴京的通用参照"。
- 老师提供的参考图版权不明，参考图本身以及带参考图的对比图、截图都不放进公开仓库。店面升级的布局图（上面表里的 png）和带布局图的对照图（`WhiteModel/Shop<n>/renders/compare.png`、`WhiteModel/StyleTest/店面升级_初始到五级_对照.png`）暂时也只留在本地。
- 八周计划已经定了（总文档第一部分 06）：试玩版做到二级，升三级后的第二天打缩小版正店比拼。`原始PDF/大纲` 还是原来的提案，没有跟着改。
