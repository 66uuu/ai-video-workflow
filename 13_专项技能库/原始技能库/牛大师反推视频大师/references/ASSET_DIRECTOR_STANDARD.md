# 资产导演与最终绑定标准

## 1. 部门职责

资产导演后台统一管理Seedance 2.5模型可见资产与绑定槽。它不改剧情、SH/D结构或情绪事实，也不新增用户端独立“资产导演审核页”。

用户仍按旧版流程完成资产确认：
`ASSET_INTAKE → CONTINUITY_REFERENCE → BLOCKING_REVIEW → OPTIONAL_BINDINGS → GEN_CONFIG → Prompt冻结后的最终BINDING_MANIFEST确认`。

## 2. 必需资产

生成前至少确认：
- 每个REPLACE人物的目标角色图；
- 至少1张用户确认的场景参考图；
- 用户确认的站位图；
- 有有效连续性时：衔接视频参考 + 连续性色卡。

站位图由执行导演设计，资产导演只在用户批准后绑定。

## 3. 衔接视频强制绑定

只要存在有效衔接视频：
- `CONTINUITY_VIDEO_REFERENCE` 必须出现在最终BINDING_MANIFEST；
- 未实际绑定即阻断生成，不得退化为“只用色卡/文字”；
- 默认取上一段正式成片末尾5.000s，允许3-5秒，最多1条；
- 用户上传完整上一段时先裁尾段，禁止整段绑定；
- 平台支持参考权重时使用低权重/辅助级；没有该参数则不虚构；
- 可关闭参考音轨时优先关闭；
- 同时绑定由尾段生成的 `CONTINUITY_COLOR_CARD`。

衔接视频只辅助00:00连续性，不负责人物身份、对白、镜头结构、后续动作或剧情。

## 4. 各资产职责

- `TARGET_ROLE_IMAGES`：人物身份与基础外观；Prompt不重复二次设计。
- `SCENE_REFERENCE_IMAGES`：建筑/空间/大型家具/固定材质。
- `PROP_REFERENCE_IMAGES`：仅对应道具外观，不改变持有手与动作事实。
- `ROLE_VOICE_REFERENCES`：仅声音身份；平台真实支持时才绑定。
- `APPROVED_BLOCKING_MAP`：只控制人物相对位置、朝向、路径、停点与关键交互区。
- `CONTINUITY_COLOR_CARD`：综合色彩与肤色/高光/黑位连续。

## 5. 最终白名单

`BINDING_MANIFEST`仅允许：
1. TARGET_ROLE_IMAGES
2. SCENE_REFERENCE_IMAGES
3. CONTINUITY_VIDEO_REFERENCE（有则必须）
4. CONTINUITY_COLOR_CARD（有连续性时）
5. APPROVED_BLOCKING_MAP
6. ROLE_VOICE_REFERENCES（有且支持）
7. PROP_REFERENCE_IMAGES（有时）
8. FINAL_VIDEO_PROMPT
9. Seedance 2.5画幅/分辨率/时长参数

禁止：当前反推视频、上一段完整成片、未批准源人物截图、内部JSON、分析日志。

## 6. 用户端资产交互必须与旧版一致

资产导演只做后台检查，不单独向用户展示“资产校对页”。

- 角色图/场景图：在 `ASSET_INTAKE` 原关卡收集。
- 衔接视频：在 `CONTINUITY_REFERENCE` 原关卡处理。
- 站位图：在 `BLOCKING_REVIEW` 原关卡让用户确认。
- 音色/道具：在 `OPTIONAL_BINDINGS` 原关卡依次询问。
- 最终是否都已绑定：只在Prompt冻结后，按旧版展示简洁 `BINDING_MANIFEST` 并再次询问是否生成。

如后台发现资产缺失，只把用户带回对应原关卡，不新增“资产导演复核”步骤。
