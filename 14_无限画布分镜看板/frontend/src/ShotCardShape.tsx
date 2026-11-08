import {
  BaseBoxShapeUtil,
  HTMLContainer,
  TLBaseShape,
  T,
} from '@tldraw/tldraw'

export type ShotCardShape = TLBaseShape<
  'shot-card',
  {
    w: number
    h: number
    shotId: string
    scene: string
    beat: string
    duration: number
    frames: number
    shotSize: string
    cameraMove: string
    dialogue: string
    speaker: string
    assets: string
    qa: string
    imageUrl: string
  }
>

const QA_COLOR: Record<string, string> = {
  PASS: '#16a34a',
  FAIL: '#dc2626',
  '未检': '#9ca3af',
}

export class ShotCardShapeUtil extends BaseBoxShapeUtil<ShotCardShape> {
  static override type = 'shot-card' as const

  static override props = {
    w: T.number,
    h: T.number,
    shotId: T.string,
    scene: T.string,
    beat: T.string,
    duration: T.number,
    frames: T.number,
    shotSize: T.string,
    cameraMove: T.string,
    dialogue: T.string,
    speaker: T.string,
    assets: T.string,
    qa: T.string,
    imageUrl: T.string,
  }

  override getDefaultProps(): ShotCardShape['props'] {
    return {
      w: 240,
      h: 360,
      shotId: '',
      scene: '',
      beat: '',
      duration: 0,
      frames: 0,
      shotSize: '',
      cameraMove: '',
      dialogue: '',
      speaker: '',
      assets: '',
      qa: '',
      imageUrl: '',
    }
  }

  override component(shape: ShotCardShape) {
    const p = shape.props
    return (
      <HTMLContainer>
        <div className="shot-card" style={{ width: p.w, height: p.h }}>
          <div className="shot-card-head">
            <span className="shot-id">{p.shotId}</span>
            <span className="shot-size">{p.shotSize}</span>
            <span className="shot-dur">{p.duration.toFixed(1)}s/{p.frames}f</span>
          </div>

          <div className="shot-card-img">
            {p.imageUrl ? (
              <img src={p.imageUrl} alt={p.shotId} />
            ) : (
              <div className="shot-card-img-empty">无首帧</div>
            )}
          </div>

          <div className="shot-card-body">
            <div className="shot-row">
              <span className="k">运镜</span>
              <span className="v">{p.cameraMove || '—'}</span>
            </div>
            {p.dialogue ? (
              <div className="shot-dialogue" title={p.speaker + '：' + p.dialogue}>
                <span className="sp">{p.speaker || '对白'}</span>
                {p.dialogue}
              </div>
            ) : null}
            <div className="shot-row">
              <span className="k">资产</span>
              <span className="v shot-assets" title={p.assets}>
                {p.assets || '—'}
              </span>
            </div>
          </div>

          <div className="shot-card-foot">
            <span className="beat">{p.beat}</span>
            {p.qa ? (
              <span
                className="qa-badge"
                style={{ background: QA_COLOR[p.qa] || '#9ca3af' }}
              >
                {p.qa}
              </span>
            ) : null}
          </div>
        </div>
      </HTMLContainer>
    )
  }

  override getIndicatorPath(shape: ShotCardShape) {
    const path = new Path2D()
    path.rect(6, 6, shape.props.w - 12, shape.props.h - 12)
    return path
  }
}