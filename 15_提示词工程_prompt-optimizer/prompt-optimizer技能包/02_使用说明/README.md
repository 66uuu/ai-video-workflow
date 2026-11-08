# prompt-optimizer 交付包使用说明

> 开源项目 **linshenkx/prompt-optimizer**（GitHub 37k+ 星，AGPL-3.0-only，v2.11.12）→ 本机化 + WorkBuddy skill 化交付。
> 交付日期：2026-10-20

## 这套东西是什么

1. **完整源码**（已克隆）：`C:/Users/<USER>/prompt-optimizer/`
   pnpm monorepo（core/ui/web/extension/desktop/mcp-server），Web 应用为 vite 8 + vue 3.5。
2. **WorkBuddy skill**（已安装到用户级目录，随时可用）：`C:/Users/<USER>/.workbuddy/skills/prompt-optimizer/`
   在任意对话里说「帮我优化这条提示词」即可触发，零配置。
3. **本地 Web 应用**（构建产物在 `packages/web/dist/`，用一键脚本启动，浏览器里图形化操作，API key 自理）。

## 怎么用

### 方式一：对话内直接优化（默认，零配置）

直接对 WorkBuddy 说：

- 「帮我优化这条提示词：<你的提示词>」
- 「把这条提示词改得更专业/更结构化」
- 「我有个提示词，帮我按 XX 方向改」（迭代）

skill 会按上游内置模板自动选模板执行，输出优化后的提示词全文。模板库共 **19 个**：

- **7 个通用模板**（对话内优化默认走这批）：通用优化 / 分析式结构优化 / 输出格式优化 / 基础优化 / 专业优化 / 步骤化规划 / 通用迭代
- **12 个图像专用模板**（说「做图片提示词」时自动切换）：文生图自然语言优化、中文 JSON 结构化、中文美学、解构创造性、图生图编辑优化（添加/删除/替换/增强四意图）、多图关系整理、设计文案替换、图像迭代、参考图复刻、参考图风格迁移等

> 图像模板的完整场景化定制（含 2D 手绘风项目的静态化/禁摄影术语纪律）见
> `../02_模板适配_图片与视频场景.md` 第 5 节与 skill 的 `references/templates.md`。

### 方式二：本地 Web 应用（图形界面）

双击 `03_Web应用/启动prompt-optimizer.cmd`（或在 skill 目录跑 `scripts/start_web.sh 8765`）：

1. 本地起静态服务（127.0.0.1:8765）并自动打开浏览器
2. 在应用设置里填**自己的 LLM API key**（本交付不提供任何密钥）
3. 正常使用优化、迭代、模板管理、历史记录等功能
4. 关闭黑色命令行窗口即停止服务

> 状态：✅ 已构建实测通过（2026-10-21 00:0x，HTTP 200，标题「提示词优化器」）。
> 构建产物在 `C:/Users/<USER>/prompt-optimizer/packages/web/dist/`；`03_Web应用/_构建产物样例_index.html` 是产物首页快照，仅作存证，运行请用启动脚本。

## 环境事实（已验证）

| 项 | 值 |
|---|---|
| Node 要求 | ^24.0.0（`.npmrc` engine-strict，必须用系统 node 24.19.0，managed node 22 会被拒） |
| pnpm | 10.6.1 |
| 构建顺序 | core → ui → web |
| Web 端口 | 8765（可改，脚本第一个参数） |
| 镜像源 | npmmirror 持续 502，已切 registry.npmjs.org |

## 成本与限制

- **成本**：0 元。软件免费（AGPL-3.0）；方式一不花 token 之外的任何费用；方式二的 LLM 调用费用取决于用户自配的 API key 用量。
- **限制**：
  - 方式二首次启动需在应用内配置 API key，否则只能看界面不能真调模型。
  - AGPL-3.0 许可证：若把本软件（含修改版）作为网络服务提供或分发衍生物，需遵守 AGPL 开源义务。
  - Web 应用只在 127.0.0.1 监听，不上公网。

## 目录结构

```
提示词/
├── 00_工作日志/工作日志.md      # 全过程记录（进度总览 + 时间线 + 待办）
├── 01_技能包/prompt-optimizer.zip   # skill 打包副本（本体已装在 ~/.workbuddy/skills/）
├── 02_使用说明/README.md        # 本文件
└── 03_Web应用/启动prompt-optimizer.cmd  # 一键启动（需 dist 构建成功）
```
