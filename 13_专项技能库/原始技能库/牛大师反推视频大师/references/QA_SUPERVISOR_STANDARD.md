# 审片监制标准

## 1. 定位

审片监制只做后台一致性验证、错误归因与退回，不生产内容，不增加新的用户交互步骤。发现问题时不得悄悄改Prompt或账本。

## 2. 生成前后台QA

在 `PROMPT_COMPILE` 完成后、进入原有 `PROMPT_USER_REVIEW` 前后台执行：
- RAW_SH/RAW_D已锁定，严格反推模式下生产计数守恒；
- 画外/短回答/重叠/跨切点对白仍存在；
- 台词、情绪、分镜均为最新用户批准revision；
- 必需资产齐全，站位已批准；
- 每个SH都有构图、动作、表演与微表情（若需要）、C、真实D/F/A、END；
- 角色身份、左右手、道具、门/容器状态无内部冲突；
- 有有效衔接视频时BINDING_MANIFEST草案包含CONTINUITY_VIDEO_REFERENCE；
- 当前反推视频和上一段完整成片没有被绑定；
- Prompt无源人物名/旧外貌/来源污染；
- Seedance 2.5、画幅、分辨率、SOURCE_TIMELINE_DURATION、BUFFER与GENERATION_DURATION合法；
- 音乐事件数=0。

结果：
- `PASS`：对用户不可见，直接进入旧版 `PROMPT_USER_REVIEW`。
- `BLOCK`：只简洁告诉用户具体问题，并退回对应**既有用户关卡**；不要创建“QA审核页”。

## 3. 生成后QA

并入旧版 `POST_GENERATION`。先裁到SOURCE_TIMELINE_DURATION，再检查：
- 时长；
- 镜头数量/顺序/关键切点；
- 人物身份是否回弹；
- 对白说话人、语言、口型与时窗；
- Blocking、位置、朝向、左右手；
- 道具与门/容器状态；
- 运镜与焦点；
- 微表情是否按节拍完成、是否过度表演；
- F/A、混响、环境连续；
- 是否出现BGM/音乐性音效；
- 最终END是否正确。

内部结论：`PASS / REGENERATE / LOCAL_FIX`。

用户端仍按旧版只看到“正式成片 + 简短验收结论 + 下一段连续性资产准备状态”。如失败，简洁说明需要重生或局部修正，不展示冗长部门报告。

## 4. 下一段资产

PASS后：
- 从正式成片裁最后5.000s；
- 标记为下一段衔接候选；
- 执行导演分析NEXT_CONTINUITY_STATE；
- 资产导演生成NEXT_CONTINUITY_COLOR_CARD并准备下一段强制绑定。
