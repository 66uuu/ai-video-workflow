# 分镜 · 无限画布看板

给「AI 生成视频」工作流加的一块**无限画布**：把一集的镜头（shot）变成可拖拽、可缩放、首帧图可视化的卡片看板，按叙事顺序自动排成一条时间轴，箭头连线。

底层用的是 [tldraw](https://github.com/tldraw/tldraw)（GitHub 上最流行的无限画布开源项目，约 3 万+ star）。整个看板本地离线运行，不碰任何外部服务。

## 一、启动

双击 `启动.bat`，它会：

1. 若 `frontend/dist` 不存在，自动 `npm install && npm run build`（首次需联网）；
2. 起一个本地服务（`server.py`，零第三方依赖，默认 `http://127.0.0.1:8080`）；
3. 打开浏览器。

停止服务：关闭标题为 `shotboard-server` 的命令窗口。

> 手动方式：`python server.py`，然后浏览器访问 `http://127.0.0.1:8080`。
> 改端口：`$env:SHOTBOARD_PORT="9000"; python server.py`（PowerShell）。

## 二、怎么用

1. 左侧点「扫描」，列出成果区里所有 `*timeline*` / `*_audit*` JSON；
2. 点一个时间轴 JSON，镜头会排成卡片看板；
3. 滚轮缩放、空格/中键拖平移、点住卡片可拖动、选中可删除。

每张卡片显示：镜号、景别、时长/帧数、首帧缩略图、运镜、台词、资产、节拍（beat）。

## 三、数据源

看板读两样东西：

- **时间轴 JSON**：标准结构是 `{ shots: [{ shot_id, shot_size, duration, frames, camera_move, dialogue, ... }] }`，也兼容「审计 JSON」（`rows[]`）和裸数组。
- **首帧图**：`server.py` 会在时间轴 JSON 所在目录向上 5 级内，找文件名形如 `S01_xxx.png`、`EP04_S01_xxx.jpg` 的图片，按镜号（`S01`）自动贴到对应卡片上。匹配不到就显示「无首帧」占位，不影响渲染。

## 四、文件结构

```
14_无限画布分镜看板/
├── frontend/            Vite + React + tldraw 前端源码
│   └── src/
│       ├── App.tsx              面板 + 加载流程
│       ├── ShotCardShape.tsx    自定义「分镜卡片」shape
│       ├── layout.ts            时间轴 JSON → 画布布局 + 箭头
│       └── api.ts               server /api 封装
├── server.py            零依赖本地服务（静态 + 读 JSON + 读首帧图）
├── 启动.bat              一键启动
└── README.md
```

## 五、安全

`server.py` 只允许访问两个白名单目录（`你的桌面\AI产物`、`你的桌面\AI生成视频`），其余路径一律 403；图片接口校验扩展名与路径，防目录穿越。仅监听 `127.0.0.1`，不对局域网开放。