// 与 backend/server.py 的 /api/* 打交道的薄封装

export interface TimelineFile {
  path: string
  name: string
  dir: string
  size: number
  mtime: number
}

export interface Shot {
  index: number
  shot_id: string
  scene: string
  beat: string
  start: number
  end: number
  start_tc: string
  end_tc: string
  duration: number
  frames: number
  shot_size: string
  camera_move: string
  assets: string
  dialogue: string
  speaker: string
  audio_note: string
  source_image: string
  video_file: string
  transition: string
}

export interface Timeline {
  episode: string
  version?: string
  title?: string
  fps: number
  total_duration: number
  total_frames: number
  shot_count: number
  shots: Shot[]
  voids?: { shot_id: string; offset: number; duration: number }[]
  [k: string]: unknown
}

async function j<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

export async function fetchRoots(): Promise<string[]> {
  const d = await j<{ roots: string[] }>('/api/roots')
  return d.roots
}

export async function scanFiles(): Promise<TimelineFile[]> {
  const d = await j<{ files: TimelineFile[] }>('/api/scan')
  return d.files
}

export async function loadJson(path: string): Promise<any> {
  const d = await j<{ ok: boolean; data: any; error?: string }>(
    '/api/load?path=' + encodeURIComponent(path)
  )
  if (!d.ok) throw new Error(d.error || 'load failed')
  return d.data
}

/** 本地图片 URL —— 走 server.py 的 /api/image，带白名单校验 */
export function imageUrl(path: string): string {
  return '/api/image?path=' + encodeURIComponent(path)
}

/** 扫描某目录附近按「Sxx」命名的首帧图，返回 {shot_id: 绝对路径} */
export async function scanImages(dir: string): Promise<Record<string, string>> {
  const d = await j<{ ok: boolean; images: Record<string, string> }>(
    '/api/scan-images?dir=' + encodeURIComponent(dir)
  )
  return d.ok ? d.images : {}
}