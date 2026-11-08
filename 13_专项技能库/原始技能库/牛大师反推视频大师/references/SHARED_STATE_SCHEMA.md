# 共享生产账本与写权限

## 1. 目的

所有专业导演使用同一份 `SHARED_PRODUCTION_STATE`，避免“一个部门写长文给下一个部门重述”造成信息丢失。源事实与生产修改分离，所有审批绑定revision。

## 2. 顶层结构

```text
PROJECT_STATE
- project_id
- fidelity_mode: STRICT_RECON | USER_MODIFIED
- westernization
- preferred_aspect_ratio
- preferred_resolution
- role_map

SEGMENT_STATE
- episode_id
- segment_id
- source_timeline_duration
- generation_buffer
- generation_duration
- SOURCE_STATE
- EXECUTION_STATE
- DIALOGUE_STATE
- PERFORMANCE_STATE
- ASSET_STATE
- PROMPT_STATE
- QA_STATE
- APPROVAL_STATE
```

## 3. SOURCE_STATE：只读事实层

仅执行导演在源审计阶段可写；锁定后所有部门只读。

```text
SOURCE_STATE
- reverse_video: ANALYSIS_ONLY
- detected_source_roles[]
- raw_sh_ledger[]
- raw_d_ledger[]
- RAW_SH_COUNT_LOCK
- RAW_D_PARENT_COUNT_LOCK
- cross_sh_dialogue_phases[]
- offscreen_dialogue_ids[]
- overlapping_dialogue_pairs[]
- uncertain_speech[]
- unresolved_shot_candidates[]
- source_emotion_evidence[]
- recon_census_locked
```

禁止任何部门为了匹配新设计而回写源事实。若后续发现假切/误听，只能回到源审计阶段，有证据地修改并重新锁定。

## 4. EXECUTION_STATE：执行导演所有

```text
EXECUTION_STATE
- revision
- SH[]
- C[]
- F[]
- A[]
- blocking
- prop_hand_state
- door_container_state
- END[]
- continuity_state_start
- continuity_state_end
- shot_script
```

执行导演可改镜头构图、动作、运镜、Blocking、物理声音和END，但不得改D正文、角色基础身份、资产绑定或情绪导演的微表情正文。

## 5. DIALOGUE_STATE：台词导演所有

```text
DIALOGUE_STATE
- revision
- source_D_map[]
- target_D[]
- speaker
- on_off_screen
- timing
- overlap
- interruption
- tone
- pause
- voice_binding_id
- localization_review_approved
```

每个目标D必须可追溯到一个源D父事件，除非项目进入USER_MODIFIED并记录用户主动新增/删除理由。

## 6. PERFORMANCE_STATE：情绪导演所有

```text
PERFORMANCE_STATE
- revision
- SOURCE_EMOTION[]
- DIRECTED_EMOTION[]
- micro_expression_cues[]
- breath_swallow_cues[]
- gaze_cues[]
- intensity
- confidence
- emotion_review_approved
```

`SOURCE_EMOTION`不可因优化而覆盖；用户修改只更新`DIRECTED_EMOTION`。

## 7. ASSET_STATE：资产导演所有

```text
ASSET_STATE
- revision
- target_role_images[]
- scene_reference_images[]
- continuity_video_reference
- continuity_color_card
- approved_blocking_map
- role_voice_references[]
- prop_reference_images[]
- BINDING_MANIFEST
- asset_review_approved
```

当前反推视频不得进入BINDING_MANIFEST。

## 8. PROMPT_STATE：提示词导演所有

```text
PROMPT_STATE
- revision
- final_video_prompt
- compiled_from_execution_revision
- compiled_from_dialogue_revision
- compiled_from_performance_revision
- compiled_from_asset_revision
- prompt_user_review_approved
- prompt_frozen
```

提示词导演只读取已批准上游状态，不反向修改上游。

## 9. QA_STATE：审片监制所有

```text
QA_STATE
- preflight_revision
- preflight_result: PASS | BLOCK
- preflight_findings[]
- postgen_result: PASS | REGENERATE | LOCAL_FIX
- postgen_findings[]
- formal_generated_video
- continuity_tail_5s
```

QA发现错误时只写finding并指明退回部门，不直接偷偷改账本。

## 10. APPROVAL_STATE：总导演所有

每个批准必须绑定具体revision：

```text
APPROVAL_STATE
- blocking_approved_revision
- dialogue_approved_revision
- emotion_approved_revision
- shot_script_approved_revision
- asset_approved_revision
- prompt_approved_revision
- generation_confirmed_revision
```

上游revision变化后，总导演必须清除受影响的下游approved_revision。
