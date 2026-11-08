# 安装与测试

## 1. 安装

将整个 `seedance-2-5-master-director-libtv` 文件夹或打包后的 `skill.zip` 上传到LibTV Skill编辑器。

## 2. 用户端交互兼容性回归（最高优先）

新版内部可多导演协作，但用户端必须与旧版逐段反推导演保持同一主流程。

输入：`我要开始第一段。`
预期：只要求上传反推视频，不介绍六个部门，不提前询问后续资产。

上传25-30秒测试视频后，用户可见顺序必须为：
1. CHARACTER_DISCOVERY / RAW_RECON_CENSUS
2. USER_ROLE_MAPPING
3. SEGMENT_META（EP/S、衔接、欧美化）
4. RECON_AUDIT（后台完成后不给冗长日志）
5. ASSET_INTAKE
6. CONTINUITY_REFERENCE
7. BLOCKING_REVIEW
8. OPTIONAL_BINDINGS（先音色、再道具）
9. GEN_CONFIG
10. DIALOGUE_LOCALIZATION_REVIEW
11. EMOTION_DIRECTION_REVIEW
12. SHOT_SCRIPT_REVIEW
13. PROMPT_USER_REVIEW
14. PROMPT_FREEZE后的最终绑定清单
15. USER_GENERATION_CONFIRM
16. POST_GENERATION

内部的DIALOGUE_SOURCE_LOCK、资产Preflight、QA_PREFLIGHT不得成为新的用户确认页。

## 3. 单一总导演界面测试

全过程检查：
- 用户不需要选择执行导演/台词导演/情绪导演等；
- 默认不出现“现在切换到某导演”的播报；
- 多部门自然语言修改由总导演内部拆分，一次统一回复；
- BLOCK时才说明问题并退回旧版已有关卡。

## 4. 自然语言路由测试

依次输入：
- `第三句更像美国年轻人说话，短一点。` → 后台只改DIALOGUE_STATE，用户仍停留/回到台词校对关卡。
- `这里不是害怕，是心虚，不要皱眉。` → 后台只改PERFORMANCE_STATE，用户仍停留/回到情绪校对关卡。
- `第二镜不要推，固定机位。` → 后台只改EXECUTION_STATE，并按旧版重新展示受影响分镜。
- `把戒指换成这张图，衔接视频一定绑定。` → 后台改ASSET_STATE，不新增资产审核页。

每次上游修改后，受影响Prompt与QA旧批准必须失效。

## 5. 衔接视频测试

有上一段正式成片尾5秒时：
- CONTINUITY_VIDEO_REFERENCE必须出现在最终BINDING_MANIFEST；
- 色卡同时绑定；
- 完整上一段不得绑定；
- 衔接视频未实际绑定时生成必须阻断；
- 用户端仍使用原有连续性/最终绑定确认，不新增单独审核页。

## 6. Prompt导演与QA测试

确认提示词导演不擅自：加/删镜头、改台词、改微表情、改道具/角色图、改连续性。

故意制造：漏短D、衔接视频未绑定、角色图串人、Prompt污染词、BGM。
预期：后台QA BLOCK并退回对应旧版关卡；PASS时用户不看到QA步骤，直接进入完整Prompt复核。

## 7. 文件大小回归

LibTV单个文本文件上限按20000保守处理。发布前检查所有 `.md/.yaml/.txt`：
- UTF-8字节数 < 18000 优先；
- 绝不能 >= 20000；
- 超限继续拆分到references，不把规则堆回SKILL.md。
