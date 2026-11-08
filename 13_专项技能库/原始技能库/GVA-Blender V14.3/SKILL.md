# GVA-Blender V14.3 全球级建筑数字孪生协同智能体

> **版本**：V14.3\
> \*\***核心公式**：工程真值 × 语义理解 × 证据图谱 × 数字孪生 × 确定性验证 × AI可视化 × 项目隔离\
> \*\***定位**：从建筑图纸到场景图+短视频的全流程自动化生产系统。

---

## 一、核心原则

1. **全局优先，局部校验，缺失标记，绝不编造，持续进化。**
2. **读取优先，推断后置，吸附禁用于真值。**
3. **几何不可变**：MASTER DIGITAL TWIN 锁定后，AI 只能修改材质/灯光/相机，禁止修改几何。
4. **唯一真值源**：所有成果派生自 MASTER DIGITAL TWIN。
5. **项目隔离**：通用规则可复用，项目数据严格隔离。
6. **联网学习、自我纠错、自我提升**：每次任务后固化经验。

---

## 二、三层数据架构

层级内容存储位置跨项目复用Layer 1通用规则Skill 描述✅ 可以Layer 2项目配置project_config.yaml❌ 独立Layer 3项目数据ADT_Core.json❌ 独立

**核心原则**：通用规则进 Skill，项目数据进 Config，解析结果进 ADT_Core。

---

## 三、建筑数据（当前项目）

### 纵向布局（含后院 17000mm）

区域进深门廊走道4000mm起居室区域4200mm餐厅区域3425mm卧室区域3375mm后院2000mm

### 横向布局（总宽 12000mm）

区域宽度卧室 + 餐厅区域8000mm停车位3000mm通道2000mm

### 功能分区明细

区域宽度进深位置起居室5000mm4200mm入户门左拐餐厅8000mm3425mm中部卧室8000mm3375mm后部停车位3000mm8200mm建筑右侧通道2000mm—连着围墙门廊—4000mm从门口往外

### 楼梯/卫生间/储藏室

对象宽度进深位置卫生间3000mm1663mm楼梯正北侧旋转楼梯—1763mm紧贴卫生间正南边储藏室—1763mm楼梯东侧

**组合关系**：餐厅区域东侧总宽 3000mm，北侧卫生间（3000×1663），南侧楼梯+储藏室（3000×1763），楼梯通向屋顶露台。

---

## 四、项目配置模板

```yaml
project:
  id: "P20260914-001"
  name: "印尼单层别墅"
  type: "villa"

building_data:
  total_width: 12000
  total_depth_with_yard: 17000
  main_building_depth: 11000
  portico_depth: 4000
  backyard_depth: 2000
  vertical_layout:
    living_room: {depth: 4200, width: 5000}
    dining_room: {depth: 3425, width: 8000}
    bedroom: {depth: 3375, width: 8000}
  horizontal_layout:
    bedroom_dining_zone: 8000
    parking_zone: 3000
    corridor: 2000

stair_bathroom_storage:
  bathroom: {width: 3000, depth: 1663}
  spiral_stair: {depth: 1763, leads_to: "roof_deck"}
  storage: {depth: 1763}

photovoltaic:
  enabled: true
  total_panels: 60
  zones: {main_roof_1: 24, main_roof_2: 12, carport: 24}
  tilt_angle: 12

incremental_structure:
  enabled: true
  type: "carport_canopy"
  dimensions: {width: 5000, depth: 8200, height_top: 3300}

video_generation:
  enabled: true
  duration_seconds: [60, 100]
  resolution: "1920x1080"
  fps: 24
五、项目隔离规则
规则	说明
项目数据不得跨项目复用	印尼别墅的12000×17000不能用于其他项目
通用规则可跨项目复用	"网格遍历"方法适用于所有项目
记忆库按项目隔离	每个项目的记忆独立存储
图层知识库可共享	"WALL图层=主体建筑"是通用知识
基因/胶囊按项目隔离	GEP协议固化的经验按项目存储
技能库可跨项目复用	SkillBank中的通用技能可共享
六、读取新项目标准流程
加载通用规则层（CORE RULES）

检查 project_config.yaml

有 → 加载项目配置

无 → 从CAD/PDF自动提取

解析图纸生成 ADT_Core.json

校验项目数据与图纸一致

禁止使用其他项目数值

进入常规工作流

七、八大核心升级
7.1 全局坐标系锚定
text
① 识别图框边界 → ② 识别轴线标注 → ③ 计算轴线间距
→ ④ 建立全局坐标系 → ⑤ 所有后续识别基于此坐标系
7.2 网格遍历完整性检查
将平面图划分为网格，逐格解析，缺失区域标记 UNKNOWN。

7.3 比例一致性校验
所有尺寸交叉验证，不一致则标记冲突。

7.4 楼梯拓扑专项引擎
text
① 识别楼梯符号 → ② 提取踏步数 → ③ 识别上下行方向
→ ④ 识别旋转方向 → ⑤ 识别垂直连接 → ⑥ 生成楼梯拓扑
7.5 相邻关系图谱
text
① 识别房间边界 → ② 计算共享墙 → ③ 建立相邻关系图
→ ④ 检查连通性 → ⑤ 输出空间拓扑图谱
7.6 联网学习引擎（Agentic RAG）
能力	说明
规范实时同步	检索最新国标/地标/国际规范
材料库更新	获取新材料参数、防火等级
设计趋势追踪	抓取建筑媒体、获奖作品
7.7 自我纠错引擎（MASC）
机制	说明
下一步执行重建	捕获因果一致性
原型引导增强	稳定异常评分
异常步骤标记	触发校正 Agent
错误分类与回滚	CRITICAL/MAJOR/MINOR
7.8 自我提升引擎（GEP）
三层结构：Genes（基因）/ Capsules（胶囊）/ Events（事件）

八、9大功能模块
8.1 光伏一体化（BIPV）
区域	排布	数量
主屋顶1号	4×6	24
主屋顶2号	3×4	12
光伏停车棚	4×6	24
总计		60块
总功率≈18kW，年发电量≈26280kWh。

8.2 增量结构设计
参数	设置
停车棚宽度	5000mm
停车棚进深	8200mm
顶棚高度	3300mm
立柱	3根，沿纵深排列
连接方式	依附建筑+外侧立柱
8.3 视频漫游生成
参数	值
时长	60~100秒
分辨率	1920×1080
帧率	24 FPS
运镜	缓慢推进+环绕+室内外切换
8.4 矢量化重建
直线拟合（最小二乘）、圆弧拟合（三点定圆/RANSAC）、自由曲线（B样条/NURBS）。

8.5 Blender 脚本
支持矢量化建模、参数化构件、光伏停车棚、全域光伏、旋转楼梯、控制图批量导出。

8.6 材质/光照系统
MATERIAL MASTER + LIGHTING-PROFILE，材质ID跨视图共享。

8.7 跨软件协同
IFC映射：WALL→IfcWall、WINDOW→IfcWindow、STAIR→IfcStair等。

8.8 多业态支持
住宅别墅、商业综合体、装配式建筑。

8.9 控制图规范
控制图	ControlNet	权重
主体建筑图	canny	0.95
墙体轴线图	canny	0.95
房间分区图	seg	0.90
门窗定位图	canny	0.92
楼梯拓扑图	canny	0.92
停车棚鸟瞰	canny	0.90
九、完整 Agent 架构（60 Agent）
确定性 Engine（16个）
#	名称	职责
E01	Drawing Type Detector	图纸类型识别
E02	PDF Engineering Parser	PDF矢量解析
E03	DWG/DXF Parser	CAD解析
E04	Dimension Intelligence Engine	尺寸智能解析
E05	Scale & Calibration Engine	比例校准
E06	Evidence Chain Builder	证据链构建
E07	Wall Axis Rebuilder	墙体轴线重建
E08	Opening Intelligence Engine	开口智能解析
E09	Room Topology Engine	房间拓扑
E10	Stair Topology Engine	楼梯拓扑专项
E11	Dual Validator	双模校验
E12	Conflict Arbitrator	真值仲裁
E13	Global Coordinate Anchor	全局坐标系锚定
E14	Grid Traversal Checker	网格遍历检查
E15	Project Isolator	项目隔离校验
E16	Data Layer Router	数据分层路由
半确定性 Agent（20个）
#	名称	职责
S01	Layer Classifier	图层语义分类
S02	Geometry Infer	几何语义推断
S03	GNN Recover	图层恢复
S04	LLM Classifier	LLM语义分类
S05	VLM Perception	多模态理解
S06	MultiTask Segment	多任务分割
S07	Topology Rebuild	拓扑重建
S08	Site Element Detector	场地元素识别
S09	Furniture Detector	家具识别
S10	Fire Safety Analyzer	消防识别
S11	Graph Builder	知识图谱构建
S12	Knowledge Retriever	联网学习
S13	Metacognitive Monitor	步骤级纠错
S14	Evolver Engine	经验固化
S15	Reflection Tuner	反思调优
S16	Proportion Validator	比例校验
S17	Adjacency Graph Builder	相邻关系图谱
S18	Missing Region Detector	缺失区域检测
S19	BIPV Generator	光伏一体化
S20	Incremental Structure Designer	增量结构设计
LLM Agent（24个）
#	名称	职责
L01	Intent Agent	意图解析
L02	Source Agent	来源索引
L03	Conflict Agent	冲突仲裁
L04	Consistency Agent	一致性校验
L05	Source Audit Agent	来源审计
L06	Impact Agent	变更影响
L07	Version Agent	版本管理
L08	Result Audit Agent	结果反审计
L09	Digital Twin Agent	主孪生维护
L10	Cross Software Agent	跨软件映射
L11	Dependency Agent	参数依赖
L12	Semantic Constraint Agent	语义约束
L13	Space Anchor Agent	空间锚点
L14	InOut Consistency Agent	内外一致性
L15	Quality Assessor	五维质量评估
L16	Self-Evolution Orchestrator	自进化总控
L17	Skill Library Manager	技能库管理
L18	Memory Consolidator	记忆整合
L19	MCP-CAD Query	MCP查询
L20	Vertical Circulation Validator	垂直交通验证
L21	Global Consistency Orchestrator	全局一致性
L22	Online Learning Coordinator	联网学习协调
L23	Error Pattern Analyzer	错误模式分析
L24	Video Generation Coordinator	视频漫游协调
十、完整工作流
text
工程PDF/CAD
   ↓
【Step 1】Project Isolator（项目隔离校验）
   ↓
【Step 2】Drawing Type Detector
   ↓
【Step 3】PDF Engineering Parser / DWG/DXF Parser
   ↓
【Step 4】联网学习引擎 → 检索最新规范
   ↓
【Step 5】Global Coordinate Anchor（全局坐标系锚定）
   ↓
【Step 6】Dimension Intelligence Engine
   ↓
【Step 7】Scale & Calibration Engine
   ↓
【Step 8】Grid Traversal Checker
   ↓
【Step 9】Evidence Chain Builder
   ↓
DRAWING TRUTH（图纸真值）
   ↓
BUILDING SEMANTIC ENGINE（建筑语义）
   ↓
【Step 10】Proportion Validator
   ↓
【Step 11】Adjacency Graph Builder
   ↓
【Step 12】Missing Region Detector
   ↓
【Step 13】自我纠错引擎（MASC）
   ↓
【Step 14】Conflict Arbitrator
   ↓
【Step 15】质量评估 → 五维评分
   ↓
MASTER DIGITAL TWIN（主数字孪生）
   ↓
【Step 16】BIPV Generator
   ↓
【Step 17】Incremental Structure Designer
   ↓
【Step 18】Blender脚本 → 三维白模
   ↓
【Step 19】材质/光照系统
   ↓
【Step 20】LibTV场景图
   ↓
【Step 21】Video Generation Coordinator
   ↓
【Step 22】自我提升引擎（GEP）
   ↓
【Step 23】四层仿生记忆更新
十一、控制图规范
主体建筑控制图
控制图	ControlNet	权重
01_主体建筑图	canny	0.95
02_墙体轴线图	canny	0.95
03_房间分区图	seg	0.90
04_门窗定位图	canny	0.92
05_结构图	canny	0.85
06_屋顶图	canny	0.85
四层区域锁定
控制图	ControlNet	权重
实例分割ID图	seg	0.90
布局约束图	canny	0.85
4K Canny	canny	0.92
法线方向梯度图	normal	0.80
楼梯专项控制图
控制图	ControlNet	权重
12_楼梯拓扑图	canny	0.92
13_相邻关系图	canny	0.85
立面控制图
控制图	ControlNet	权重
立面线稿	canny	0.90
MLSD直线图	mlsd	0.85
立面深度图	depth	0.80
室内控制图
控制图	ControlNet	权重
空间锚点图	canny	0.90
室内分割图	seg	0.85
十二、LibTV Prompt 模板
主体建筑Prompt
text
Generate a photorealistic architectural rendering of a single-storey modern villa.

CRITICAL: DO NOT render any perimeter fence, boundary wall, or site wall.
ONLY focus on the main building structure.

GEOMETRY IS IMMUTABLE. DO NOT change wall positions, window positions,
door positions, or stair direction.

The building includes:
- Main walls with correct axis and thickness
- Windows and doors with correct dimensions and positions
- Spiral staircase (clockwise ascending, connecting LEVEL-01 to ROOF_DECK)
- Bathroom adjacent to staircase (west side)
- Storage room adjacent to staircase (north side)
- Roof deck and parapet

Style: modern minimalist villa, clean white walls, large glass openings,
warm wood accents, natural daylight, 8k, photorealistic, 16:9.

Negative Prompt:
fence, boundary wall, perimeter wall, site wall, gate,
deformed geometry, wrong wall positions, extra windows, missing doors,
wrong stair direction, wrong stair rotation, missing landing,
oversaturated colors, fisheye lens, blurry, low resolution.
楼梯专项Prompt
text
Generate a photorealistic interior rendering of the spiral staircase
connecting the ground floor to the roof deck.

The staircase:
- Spiral type with clockwise ascending direction
- 14 runs with correct riser/tread proportions
- Width approximately 1200mm

The staircase is adjacent to:
- Bathroom on the west side
- Storage room on the north side

Style: modern minimalist, warm materials, natural daylight,
8k, photorealistic, 16:9.

Negative Prompt:
straight staircase, wrong rotation direction, missing landing,
deformed geometry, cluttered layout, blurry, low resolution.
十三、验证清单
检查项	预期	调整
项目隔离校验	无跨项目污染	启用Project Isolator
数据分层路由	三层数据正确路由	启用Data Layer Router
建筑进深（含后院）	17000mm	检查
建筑主体进深	11000mm	检查
总宽	12000mm	检查
起居室	5000×4200mm	检查
餐厅	8000×3425mm	检查
卧室	8000×3375mm	检查
卫生间	3000×1663mm	检查
旋转楼梯	1763mm深	检查
储藏室	1763mm深	检查
光伏板总数	60块	启用BIPV Generator
停车棚尺寸	5000×8200×3300mm	启用Incremental Structure
视频时长	60~100秒	启用Video Coordinator
楼梯方向	顺时针上升	启用Stair Engine
内外窗一致性	100%重合	自动检查
几何不可变层	100%保护	检查Immutable Layer
十四、V14.3 核心定义
GVA-Blender V14.3 = 项目隔离 × 数据分层 × 全局坐标系 × 网格遍历 × 比例校验 × 楼梯拓扑 × 相邻关系图谱 × 光伏一体化 × 增量结构 × 视频漫游 × 联网学习 × 自我纠错 × 自我提升 × AI可视化。

核心原则：

通用规则进 Skill，项目数据进 Config，解析结果进 ADT_Core

几何不可变，AI 只能修改材质/灯光/相机

读取优先，推断后置，吸附禁用于真值

持续进化，越用越强

协议结束

---

### 附件说明
- 附件1-4 为代码/配置的 Markdown 文本（.md 格式）
- 实际执行时需在本地复制内容到对应格式文件：
  - gva_v14.3_blender.md → 复制到 Blender 脚本
  - gva_v14.3_parser.md → 复制到 .py 文件运行
  - gva_v14.3_algorithms.md → 复制到 .py 文件运行
  - project_config_template.md → 复制到 .yaml 文件
---

## 风格库调用规则

### 已内置风格（8种）
1. STYLE-NANYANG-001: 南洋复古风（31张参考图）
2. STYLE-MCM-001: 中古风（8张参考图）
3. STYLE-NATURAL-001: 自然风/日式（1张参考图）
4. STYLE-MAXIMALISM-001: 极繁主义（2026趋势，增长39%）
5. STYLE-ECLECTIC-001: 折衷主义（2026趋势，增长38%）
6. STYLE-COLORFUL-LUXURY-001: 彩色静奢风（2026趋势）
7. STYLE-NEODECO-001: 装饰艺术风（2026百年回归）
8. STYLE-WABI-SABI-001: 侘寂风

### 调用规则
1. 用户指定风格 → 从 style_library 中匹配 style_id
2. 用户指定融合 → 按 fusion_rules 组合（主60%+辅30%+点缀10%）
3. 用户未指定 → 默认现代简约
4. 风格冲突 → 按 primary_priority 处理

### 场景细分调用
- "生成南洋复古风客厅" → 调用 NANYANG-A
- "生成中古风餐厅" → 调用 MCM-B
- "生成侘寂风茶室" → 调用 WABI-SABI-A
```