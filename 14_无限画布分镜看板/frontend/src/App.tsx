import { useCallback, useRef, useState } from 'react'
import { Tldraw, type Editor } from '@tldraw/tldraw'
import { ShotCardShapeUtil } from './ShotCardShape'
import { buildTimeline } from './layout'
import {
  scanFiles,
  loadJson,
  imageUrl,
  scanImages,
  type TimelineFile,
  type Timeline,
  type Shot,
} from './api'

const shapeUtils = [ShotCardShapeUtil]

function mk(shots: Shot[]): Timeline {
  return {
    episode: '',
    fps: 24,
    total_duration: 0,
    total_frames: 0,
    shot_count: shots.length,
    shots,
  }
}

/** 兼容三种来源：时间轴 JSON（shots）、审计 JSON（rows）、裸数组 */
function normalize(data: any): Timeline {
  if (Array.isArray(data)) {
    return mk(data.map((s, i) => ({ ...s, shot_id: s.shot_id ?? s.shot ?? `S${i + 1}` })))
  }
  if (data && Array.isArray(data.shots)) {
    return data as Timeline
  }
  if (data && Array.isArray(data.rows)) {
    const shots: Shot[] = data.rows.map((r: any, i: number) => ({
      index: i + 1,
      shot_id: r.shot ?? r.shot_id ?? `S${i + 1}`,
      scene: r.scene ?? '',
      beat: r.beat ?? '',
      start: r.start ?? 0,
      end: r.end ?? 0,
      start_tc: r.start_tc ?? '',
      end_tc: r.end_tc ?? '',
      duration: r.dur ?? r.duration ?? 0,
      frames: r.frames ?? 0,
      shot_size: r.size ?? r.shot_size ?? '',
      camera_move: r.cam ?? r.camera_move ?? '',
      assets: r.assets ?? '',
      dialogue: r.dialogue ?? '',
      speaker: r.speaker ?? '',
      audio_note: '',
      source_image: '',
      video_file: '',
      transition: 'cut',
    }))
    return mk(shots)
  }
  throw new Error('无法识别的 JSON 结构：需要 shots 或 rows 数组')
}

export default function App() {
  const editorRef = useRef<Editor | null>(null)
  const [files, setFiles] = useState<TimelineFile[]>([])
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)

  const refresh = useCallback(async () => {
    setBusy(true)
    setStatus('扫描中…')
    try {
      setFiles(await scanFiles())
      setStatus('扫描完成')
    } catch (e) {
      setStatus('扫描失败：' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setBusy(false)
    }
  }, [])

  const openFile = useCallback(async (f: TimelineFile) => {
    const ed = editorRef.current
    if (!ed) {
      setStatus('画布尚未就绪，稍等再试')
      return
    }
    setBusy(true)
    setStatus('加载：' + f.name)
    try {
      const data = await loadJson(f.path)
      const timeline = normalize(data)
      const imgs = await scanImages(f.dir)
      const urlMap: Record<string, string> = {}
      for (const sid of timeline.shots.map((s) => s.shot_id)) {
        if (imgs[sid]) urlMap[sid] = imageUrl(imgs[sid])
      }
      const n = buildTimeline(ed, timeline, urlMap)
      setStatus(`已渲染 ${n} 镜 · 首帧命中 ${Object.keys(urlMap).length}`)
    } catch (e) {
      setStatus('失败：' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setBusy(false)
    }
  }, [])

  return (
    <div className="app">
      {panelOpen && (
        <aside className="panel">
          <header>
            <h1>分镜 · 无限画布</h1>
            <button onClick={refresh} disabled={busy}>
              {busy ? '…' : '扫描'}
            </button>
          </header>
          <p className="status">{status || '就绪'}</p>
          <ul className="file-list">
            {files.map((f) => (
              <li key={f.path}>
                <button onClick={() => openFile(f)} title={f.path}>
                  <span className="fname">{f.name}</span>
                  <span className="fdir">{f.dir}</span>
                </button>
              </li>
            ))}
          </ul>
          {files.length === 0 && !busy && (
            <p className="hint">点「扫描」列出成果区里的时间轴 / 审计 JSON</p>
          )}
          <div className="tips">
            <p>选一个 JSON，镜头会排成卡片看板。</p>
            <p>滚轮缩放 · 空格拖平移 · 点住卡片拖动。</p>
          </div>
        </aside>
      )}
      <div className="canvas">
        <button
          className="toggle"
          onClick={() => setPanelOpen((v) => !v)}
          title={panelOpen ? '收起面板' : '展开面板'}
        >
          {panelOpen ? '‹' : '›'}
        </button>
        <Tldraw
          shapeUtils={shapeUtils}
          onMount={(editor) => {
            editorRef.current = editor
          }}
        />
      </div>
    </div>
  )
}