import { Editor } from '@tldraw/tldraw'
import type { Timeline } from './api'

const CARD_W = 240
const CARD_H = 360
const GAP_X = 90

export function clearCanvas(editor: Editor) {
  editor.selectAll()
  editor.deleteShapes(editor.getSelectedShapeIds())
}

export function buildTimeline(
  editor: Editor,
  timeline: Timeline,
  images: Record<string, string>
): number {
  clearCanvas(editor)

  const shots = timeline.shots
  const ids: string[] = []
  const xs: number[] = []

  shots.forEach((s, i) => {
    const x = i * (CARD_W + GAP_X)
    const y = 0
    xs.push(x)
    const rec = editor.createShape({
      type: 'shot-card',
      x,
      y,
      props: {
        w: CARD_W,
        h: CARD_H,
        shotId: s.shot_id,
        scene: s.scene,
        beat: s.beat,
        duration: s.duration,
        frames: s.frames,
        shotSize: s.shot_size,
        cameraMove: s.camera_move,
        dialogue: s.dialogue,
        speaker: s.speaker,
        assets: s.assets,
        qa: '',
        imageUrl: images[s.shot_id] || '',
      },
    })
    if (rec) ids.push(rec.id)
  })

  // 相邻卡片之间画一条箭头（自由点，不绑定 shape）
  for (let i = 0; i < ids.length - 1; i++) {
    const x1 = xs[i] + CARD_W + 8
    const y1 = CARD_H / 2
    const x2 = xs[i + 1] - 8
    const y2 = CARD_H / 2
    editor.createShape({
      type: 'arrow',
      x: Math.min(x1, x2),
      y: y1 - 10,
      props: {
        kind: 'arc',
        start: { x: x1, y: y1 },
        end: { x: x2, y: y2 },
        color: 'black',
        size: 's',
        bend: 0,
        arrowheadStart: 'none',
        arrowheadEnd: 'arrow',
      },
    })
  }

  editor.zoomToFit({ duration: 0 })
  return ids.length
}