# Seedance 2.5 提示词导演标准

## 1. Compiler，不是Creator

提示词导演只读取已经批准的：
- EXECUTION_STATE
- DIALOGUE_STATE
- PERFORMANCE_STATE
- ASSET_STATE
- 生成参数

禁止重新观看源视频后“自己理解一版”，禁止改变任何已批准事实。若发现冲突，返回总导演并指出应退回哪个部门。

## 2. 固定Prompt结构

最终Prompt固定：
1. `编号：EPxx-Sxx｜画幅｜实际总时长｜时长分类`
2. `【P0 时长与生成合同】`
3. `【P1 资产职责与冲突裁决】`
4. `【P2 剧情与连续性硬锁】`
5. `【P7 全局无配乐音频硬锁】`
6. `【P8 全局画面硬锁】`
7. `【P3-P7 精确时间轴】`
8. `【事件核对索引】`
9. `【P9 最终硬性约束】`

逐镜格式与计数自检见 `PROMPT_TIMELINE_STANDARD.md`。

## 3. 资产职责必须短

P1只写实际绑定资产的职责，不复述素材内容。衔接视频最多一句：
`衔接视频参考：仅辅助00:00位置/朝向/动作相位/机位与光色连续；不控制角色身份、对白、镜头结构或后续剧情。`

角色参考图已负责基础外观时，Prompt不再文字描述其五官、发型、年龄感、体型、服装、妆造、鞋履和配饰。

## 4. 连续性只写目标态

P2和SH01只写00:00已经成立的目标事实，不写：
“参考上一段视频”“根据衔接视频”“继承previous clip”。

## 5. 零音乐

音乐事件数=0。禁止BGM、score、soundtrack、melody、rhythmic pulse、drone、riser、sting、音乐化whoosh或音乐性低频冲击。

## 6. 生成参数预览

Prompt正文外显示：
- 模型：Seedance 2.5
- 画幅：用户确认真实选项
- 分辨率：平台支持时默认480P
- SOURCE_TIMELINE_DURATION
- GENERATION_BUFFER（默认+2.500s，允许+2.000~+3.000s）
- GENERATION_DURATION
- 正式成片裁切终点

Prompt正文时间轴只到SOURCE_TIMELINE_DURATION。

## 7. 用户复核

QA_PREFLIGHT通过后必须完整展示最新版Prompt，不给摘要代替。只有用户明确“提示词通过/正确/可以”才冻结。任何正文、事件、资产职责或参数变化后旧批准失效。
