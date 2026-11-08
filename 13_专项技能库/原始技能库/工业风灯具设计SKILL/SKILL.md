---

## name: parametric-lighting-design-generator\\

description: 生成参数化、多材质的超写实灯具设计指令。支持壁挂灯、天顶吊灯、台灯三大系列。集成文生图、造型元素扩展、以及线稿自动渲染（配合ControlNet）三大工作流功能。\
version: 1.0.0\
product: SZDSAI 工业设计 / 数字化照明设计专版

# SKILL：参数化多材质灯具设计生成器

## 一、SKILL定位与核心能力

本SKILL专为工业设计师、照明设计师及数字媒体艺术创作者打造，旨在通过参数化设计语言与多元材质的碰撞，生成**超写实（Photorealistic）** 级别的灯具设计方案。核心能力覆盖：

**三大灯具系列**：

1. 天顶吊灯（Ceiling Pendants / Chandeliers） - 强调空间张力与下垂视觉延展。
2. 墙壁挂灯（Wall Sconces / Mounted Lamps） - 强调环境洗墙光效与墙面构成。
3. 桌面台灯（Table Lamps / Desk Lights） - 强调近景细节、人体工学与交互连接。

**三大核心功能模块**：

1. **文生图概念设计**：直接生成无AI感、无塑料渲染感的专业摄影级灯具概念图。
2. **造型元素分解与扩展**：提取参数化节点、骨架、切片阵列等局部元素，为3D建模（如Rhino/Grasshopper）提供单元模块参考。
3. **线稿自动渲染图**：提供精准的提示词与控制网络（ControlNet）参数设置，将设计师手绘草图/CAD线稿完美转化为超写实材质效果图。

## 二、核心输出标准——工业级超写实（无AI味）

所有生成的图像提示词必须强制导向工业级产品摄影输出，拒绝一切劣质3D渲染感或模糊结构。

### 2.1 强制风格指令（必含）

photorealistic, industrial design product photography, hyper-realistic, 8K, macro-surface detail, real-world material fidelity, physically-based rendering (PBR), studio lighting, sharp focus, precise structural connections, no CGI look, no stylized rendering.

### 2.2 负面提示词（必用）

CGI, computer generated, plastic look, fake materials, distorted geometry, blurred details, asymmetrical logic, floating parts, unstable structure, AI-generated artifacts, over-saturated, cartoon.

## 三、参数化与多材质参数体系（模块词库）

基于广泛的制造业与参数化设计工艺，本系统建立以下参数库供生成时组合调用：

### 1. 参数化结构语言 (Parametric Structures)

类别关键词 / 概念说明**切片与阵列**Waffle structure (华夫切片), Contour crafting, 放射状渐变 (Radial gradient array)适合木板、亚克力板材的激光切割组装**拓扑与多面体**Voronoi tessellation (泰森多边形), Geodesic dome (测地线穹顶), 折纸曲面 (Origami surface)展现复杂的透光孔洞与未来感**仿生与流体**Twisting helix (扭转螺旋), Bionic veins (有机仿生脉络), 蘑菇褶皱 (Mushroom gills)优雅的曲线形态，适合3D打印或玻璃吹制**模块化节点**Modular interlocking joints (模块化互锁节点), Space frame (空间网架)突出工业感与组装逻辑

### 2. 多材质组合系统 (Material Combinations)

灯具的高级感来源于材质对比。推荐采用“结构主材 + 透光辅材 + 连接件”的三维组合：

类别关键词（英文为佳）特质描述**骨架/主体材质**Anodized Aluminum (阳极氧化铝), Weathered Corten Steel (耐候钢), Steam-bent Walnut (蒸汽弯曲胡桃木), Brushed Brass (拉丝黄铜), Carbon Fiber (碳纤维)提供力学支撑与工业质感**透光/折射材质**Italian Alabaster (意大利雪花石膏 - 呈现天然矿石透光感), Frosted Polycarbonate (磨砂聚碳酸酯), Blown Glass (吹制玻璃), 3D Printed ABS (3D打印半透ABS)决定光线的漫反射与折射效果**编织/柔性材质**Bamboo weave (竹篾编织), Tension fabric (张力膜材), Tyvek paper (特卫强纸)带来温暖的自然光影与漫射光

### 3. 文化符号与肌理 (Cultural & Surface Textures)

类别关键词 / 概念**东方美学融合**唐代团花纹镂空 (Tang Dynasty floral motif cutouts), 榫卯结构转换 (Tenon and mortise inspiration)**工业机械复古**Steampunk pipes (蒸汽朋克管道), Exposed copper wiring (外露纯铜走线), Knurled metal knobs (滚花金属旋钮)**自然微观肌理**Sandblasted surface (喷砂表面), Wood grain finish (木纹触感), Matte ceramic (哑光陶瓷)

---

## 四、三大工作流功能与提示词模板

### 功能一：文生图 (Text-to-Image Concept Design)

**框架**：\[超写实锚定\] + \[灯具类型与使用场景\] + \[参数化结构\] + \[材质与表面处理\] + \[光源与细节\] + \[参数控制\]

**生成示例（天顶吊灯 - 石膏与黄铜参数化阵列）**：

> Photorealistic, industrial design product photography. A large-scale parametric ceiling pendant lamp suspended in a minimalist concrete interior. The design features a twisting helix structure composed of individual Italian Alabaster (雪花石膏) blades, connected by precision-machined brushed brass (拉丝黄铜) mechanical joints. Warm 3000K LED light emanates from the central core, illuminating the natural translucent veining of the alabaster. Studio lighting, precise structural connections, macro-surface detail, 8K, ultra-detailed, no CGI look.

### 功能二：造型元素提取与扩展 (Modeling Elements Expansion)

此功能用于为设计师提取单个灯具模块或连接件的特写，方便后续在Rhino/Grasshopper中复现。

**生成示例（模块化互锁节点特写）**：

> Macro shot, extreme close-up product photography. A single parametric joint node for a modern lamp assembly. The component features a complex Voronoi topology, 3D printed in matte black ABS material, interlocking seamlessly with a steam-bent walnut wood strut. Embedded hidden LED strip detail. Clean white background, technical design study, sharp focus on the material texture and gap tolerances. 8K, hyper-realistic.

### 功能三：线稿自动渲染图 (Line-art Auto-Render Workflow)

当设计师输入手绘线稿或CAD轮廓时，使用此模块输出对应的渲染提示词与本地AI工具（如ComfyUI）的参数配置指导。

**【系统操作配置指南】（作为辅助信息输出给用户）：**

- **模型/节点流建议**：推荐在 ComfyUI 工作流中使用 `ControlNet Lineart` 或 `ControlNet Canny`。
- **权重参数**：ControlNet 权重设置在 0.65 - 0.8 之间（保留参数化造型的同时赋予材质想象空间）。
- **采样器**：推荐 KSampler 使用 `DPM++ 2M Karras`，Steps 30-40，CFG Scale 6-7。在充足显存下（如24G VRAM设备），务必接入高分辨率修复（Highres. fix）节点，重绘幅度设为 0.3-0.4，以彻底消除线稿边缘的锯齿感并强化材质微观纹理。

**配合线稿的渲染提示词示例（桌面台灯 - 仿生叶脉结构）**：

> Photorealistic render of a contemporary table lamp, perfectly adhering to the provided line art structure. The shade features an organic bionic vein network (有机仿生脉络) made of frosted polycarbonate, intricately incorporating Tang Dynasty floral motif cutouts (唐代团花纹镂空) mapped parametrically across the curved surface. Resting on a heavy brushed copper cylindrical base with knurled mechanical switches. Soft ambient glow from within, studio lighting, hyper-realistic material fidelity, 8K resolution, architectural digest style.

---

## 五、SKILL 交互运行逻辑 (System Prompt Instructions)

作为AI Agent，当用户调用本SKILL时，请遵循以下交互逻辑：

1. **需求诊断**：依据用户需要的灯具类型（壁灯/吊灯/台灯），倾向的材质系统，自动选择三大功能模块中的哪一个。
2. **多形态组合设计**：若用户未指定细节，请利用**第四节**的参数库，随机组合出具有强烈工业设计感与参数化特征的设定（例如：将传统的“竹篾编织”与硬核的“阳极氧化铝CNC节点”结合）。
3. 
4. **输出格式**：
   - 如果用户选择【功能一】（文生图），直接输出一段中文超写实提示词。
   - 如果用户选择【功能二】（提供单个几何体造型零部件），则输出由单个零部件/模块单元衍生的组合而成的灯具作品的提示词，强调组装的复制与组合的结构逻辑，输出中文超写实提示词。
   - 如果用户选择【功能三】（提供灯具设计线稿），则依据线稿的造型输出可以完整渲染设计稿成为写实灯具的中文超写实提示词。