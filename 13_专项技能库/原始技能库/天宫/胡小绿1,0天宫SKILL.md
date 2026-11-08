---

## name: create-grand-chinese-fantasy description: Create and refine grand Chinese fantasy scene prompts and image-to-video prompts with mountain-scale Chinese architecture, surreal spatial laws, cloud seas, deserts, grasslands, waterfalls, and one to three female immortal figures. Use when the user asks for 宏大古风, 中式幻想, 仙家云海, 天宫 or other Chinese halls and gates, surreal Midjourney scene prompts, analysis of generated scene images, or a 5-second cinematic video prompt from an uploaded image.

# Create Grand Chinese Fantasy

Create Chinese mythic images that feel immense and impossible without becoming busy, ordinary, or tourist-like. Preserve the accepted visual language across still prompts and image-to-video motion.

## Route the request

1. Read references/visual-language.md for every request.
2. For new or revised image prompts, also read references/still-prompts.md.
3. For an uploaded image or image folder that needs a video prompt, also read references/video-motion.md.
4. For tone calibration or when results drift, read references/accepted-examples.md.
5. If the request spans still generation and video generation, complete the still prompt first, then derive motion from the selected image rather than inventing an unrelated shot.

## Inspect visual input

- When the user uploads an image, inspect it before writing the prompt.
- When the user names a folder, list supported image files and inspect all relevant images. Use a contact sheet for large sets, then open representative images when details are unclear.
- Identify the architecture, environment, number and placement of women, depth layers, dominant geometry, light direction, and the single impossible spatial rule.
- Do not infer unseen story elements that would add visual clutter.

## Produce still prompts

- Write finished Midjourney prompts in English unless the user requests another language.
- Lead with the impossible spatial premise, then architecture, environment, women, composition, light, material quality, and parameters.
- Keep exactly one dominant architectural subject and one dominant environmental field.
- Keep one to three female immortal or female traveler figures unless the user specifies otherwise.
- Make the women visually tiny and use them as scale anchors rather than portrait subjects.
- Prefer credible jade, timber, stone, silk, water, sand, grass, mist, and cloud textures inside an impossible world.
- Use cinematic mythological concept art language. Avoid photographic-tourism language.
- Vary Chinese elements beyond palaces: gatehouses, ancestral halls, ritual halls, moon gates, corridors, covered bridges, academies, drum towers, observatories, walls, pavilions, pagodas, terraces, and stairways.
- Return the requested number of prompts without extra alternatives.
- End every Midjourney still-image prompt with the V8.2 version parameter `--v 8.2`. Do not substitute another version or omit the version unless the user explicitly requests it.

## Produce image-to-video prompts

- Follow references/video-motion.md as the authoritative image-to-video template. Do not override its camera speed, motion hierarchy, output length, or stability constraints with other guidance in this skill.
- Preserve the uploaded image as the first frame and inspect it before selecting the single main camera move.
- Output only the finished Chinese prompt when the user asks for a directly usable result.

## Quality gate

Reject and rewrite any output that has one or more of these problems:

- It could be mistaken for a real tourist destination or ordinary landscape photograph.
- The architecture is merely large rather than physically impossible or mountain-scale.
- Multiple wonders compete for attention.
- Crowds, caravans, cities, lantern seas, dense props, or decorative clutter appear without a request.
- More than three people appear, or the women become the main portrait subject.
- The scene loses recognizable Chinese architectural logic.
- The video move is chaotic, tourist-like, drone-like, or combines several unrelated camera moves.
- Buildings deform, clouds move at one flat speed, or fabric motion overwhelms the scene.

## Final check

Before responding, confirm:

- one impossible spatial law;
- one dominant Chinese architectural subject;
- one dominant environment;
- one to three women used as scale anchors;
- large negative space and a clear silhouette;
- believable materials inside an unreal divine world;
- no tourist-photo phrasing;
- for video, one slow, stable camera move selected according to the uploaded composition.