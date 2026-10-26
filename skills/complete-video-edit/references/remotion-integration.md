# 按需 Remotion 双照片包装

只有用户需要复杂照片动画时才走本流程。基础精剪继续使用 `scripts/edit.py`，
不安装或加载 Node/Remotion。照片不延长叙述、不改变剪辑顺序；不要自动添加字幕、
章节、配乐或片尾。重要动作正在发生时换插入窗口或采用其他布局，不能用照片遮掉。

## 先区分三件事

1. **Agent Skills**：教 Codex 如何制作；先看当前会话技能目录，有官方 Remotion
   插件或技能就直接加载。不为每条视频重新安装，不把上游内容复制进本仓库。
2. **工程**：本 Skill 的 `remotion/` 是独立、可复用的小模板，并非完整剪辑器。
3. **运行环境**：Node.js 22+、工程 npm 依赖、渲染浏览器、FFmpeg/FFprobe。
   看见 Skill 不等于能渲染；需要用实际预览/导出验证。

官方上游：[remotion-dev/skills](https://github.com/remotion-dev/skills)，
[官方安装说明](https://www.remotion.dev/docs/ai/skills)。缺失且用户授权安装时：

```powershell
# 查看可用项，不安装技能
npx skills add remotion-dev/skills --list
# 项目级：从需要这些技能的项目目录执行
npx skills add remotion-dev/skills --agent codex
# 或全局安装（两种作用域按需选一种）
npx skills add remotion-dev/skills --agent codex --global
# 查看 CLI 安装记录
npx skills list --agent codex
npx skills list --agent codex --global
```

`skills` CLI 的 Codex 路径是项目 `.agents/skills/` 和用户 `~/.agents/skills/`；
见[上游路径表](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)和
[命令说明](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)。已有插件或
自定义/旧版安装位置不应据此搬迁；CLI 列表也不涵盖所有插件。最终检查当前 Codex
会话是否实际列出、能读取对应技能；必要时重启会话。目录存在不是“已可调用”的证据。

优先加载 `remotion-best-practices` 路由，再按任务加载：

| 工作 | 官方技能 |
| --- | --- |
| 新工程/新合成 | `remotion-create` |
| 布局、动画与时间轴 | `remotion-markup` |
| 交互预览 | `remotion-studio` |
| 导出视频或关键帧 | `remotion-render` |
| 查询 API 或升级依赖 | `remotion-docs` / `remotion-upgrade` |

不默认加载字幕技能，不让通用示例覆盖用户“完整内容、原序、原声、无默认装饰”的要求。
安装/更新仍遵循本 Skill 的环境授权规则。默认不使用 Git submodule：它只挂载文件，
并不能保证 Agent 发现，而且增加迁移维护步骤。真正需要离线分发时再单独设计。

## Windows 一次性准备

从实际安装的完整 Skill 目录执行，示例保留仓库当前的安装路径约定；如果安装位置不同
则换成实际路径。不要在每条视频下重新下载整个项目：

```powershell
Set-Location "$env:USERPROFILE\.codex\skills\complete-video-edit"
python --version
node --version
ffmpeg -version
ffprobe -version
Set-Location remotion
npm ci
npm run check
npm run browser
Set-Location ..
```

Python 3.10+，推荐既有的 3.12。Remotion 包统一锁定为 4.0.539，依赖以
`package-lock.json` 为准。`npm run browser` 是一次性下载工程缓存浏览器的明确步骤；
导出不会自动安装缺失依赖或浏览器。可用 `REMOTION_BROWSER_EXECUTABLE` 指定兼容浏览器。
升级时同步全部 Remotion 包并重新验证，不能只升级其中一个。

迁移时复制完整 Skill，包括 `remotion/` 的源码及锁文件；在新主机重新 `npm ci` 和
准备浏览器。不要复制另一平台的 `node_modules`。不改动原有 Whisper 依赖锁和转写环境。

## 计划：单独配置，复用精剪时间轴

示例见 [visual-plan.json](../examples/visual-plan.json)。不要把包装字段写进
`edit-plan.json` v1；该格式仍拒绝未知字段。

`edit_result` 引用 `edit.py render` 的已通过验收目录。相对目录和照片路径都相对于
视觉计划文件。准备阶段复核母版、计划和时间映射指纹，但不修改原来的验收报告。

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `edit_result` | 精剪结果目录，本地路径 |
| `effects` | 1–32 个不重叠的 `photo-pair`；没有效果直接交付母版 |
| `id` / `type` | 唯一非空标识 / 固定 `photo-pair` |
| `photos` | 两张本地静态 PNG、JPEG 或 WebP；按提供顺序，不裁照片 |
| `timebase` | `output` 或 `source` |
| `start_frame` / `duration_frames` | 非负起始帧 / 正持续帧数，半开区间 |
| `transition_frames` | 可选，每次过渡帧数；四次过渡加三个至少一帧的停留须装进窗口 |
| `overview_scale` | 可选，概览照片框相对画幅大小，0.1–0.42，默认 0.36 |
| `focus_scale` | 可选，放大照片框相对画幅大小，0.5–0.95，默认 0.88 |
| `layer` | 可选，正整数，默认 1；首版仍不接受效果窗口重叠 |

宽高、帧率、总帧数继承母版，不在视觉计划里重复维护。`source` 的帧号使用精剪工具
归一化后的源帧网格，查 `timeline.json`，不能直接用 VFR 文件的解码帧序号替代。
源区间必须完整落在一个保留段内；删除位置或跨剪口的窗口报错，由 Codex/人工重新定位。
`output` 的帧号就是成片帧号，效果不能超出总时长。没有隐式变速、删段、自动挪位置。

## 准备、预览与输出

```powershell
# 从 Skill 根目录执行。目录必须是新路径。
python scripts/visual.py prepare 'C:\素材\visual-plan.json' --output 'C:\素材\包装工程-v1'
# 预览用同一份 props.json 和已暂存素材
Set-Location remotion
npm run studio -- 'C:\素材\包装工程-v1'
# 浏览器访问命令实际打印的 URL，选择 PhotoPair；端口可能不是 3000
```

另一个终端从 Skill 根目录导出（Studio 可以继续运行）：

```powershell
# 局部预览：从第 40 帧到第 280 帧，不含 280，保留动画的全局时序
python scripts/visual.py render 'C:\素材\包装工程-v1' --output 'C:\素材\预览-v1' --start-frame 40 --end-frame 280
# 完整输出及阶段关键帧
python scripts/visual.py render 'C:\素材\包装工程-v1' --output 'C:\素材\包装成片-v1' --stills
```

上面的帧数只是用法示例，必须换成实际母版允许的范围。`prepare` 和 `render` 可传
`--ffmpeg`、`--ffprobe`；`render` 还可传 `--node` 指定可执行文件。脚本输出 UTF-8 JSON，
成功退出 0，业务失败退出 1，命令行用法错误退出 2。Windows 用 JSON 文件传配置，
避免在 shell 内嵌 JSON 引号。[Remotion 官方 CLI 说明](https://www.remotion.dev/docs/cli/render)

准备目录保存 `visual-plan.json`、派生 `props.json`、`workspace.json` 及 `public/` 素材快照。
照片先探测/解码，再报告准备成功。指纹锁定快照，修改计划后重新准备新目录，不手工篡改
旧的 props 或暂存素材。Studio 可用于查看，但本模板以计划文件为权威，不承诺 Studio
直接编辑能回写视觉计划。默认浏览器预览保留母版声音。

输出目录保存 `run.json`、`props.json`、`workspace-snapshot.json`、`verification.json`，
通过后发布 `output.mp4`。`--stills` 额外保存共同出现、第一张最大、交接、第二张最大、
返回主画面的关键帧；只保存本次范围内的帧。失败保留报告并清理临时 MP4；强制结束进程
可能留下 partial 文件，不能当作成片交付。

## 原声、检查与限制

Remotion 只渲染画面；完整导出由 FFmpeg **复制母版 AAC 音轨**，比较压缩音频数据 SHA-256。
无音轨母版仍无音轨。局部预览为准确裁切而重新编码 AAC，记录 `trimmed_preview_aac`，
不能声称预览的音频数据与整条母版相同。两种输出都检查帧数、时长、分辨率、帧率、音轨
及完整解码。不会修改原声内容或自动配乐，但实际剪口和听感仍需审查。

视觉层新增一次有损画面编码；浏览器颜色处理不保证逐像素等同母版。不把它用于无损修复、
HDR 或色彩校准工作。首版不做多轨编辑、重叠效果、重排素材、插入额外时长或局部缓存。

技术报告保持 `pending_human_review`。检查照片完整构图、关键动作是否被遮挡、过渡是否自然、
原声是否连续；不能用技术通过宣称内容已听辨。交付说明实际引擎是 Remotion 画面加 FFmpeg
音轨封装。包含个人素材的准备目录、输出和日志保存在仓库外，不提交 GitHub。

## 开发验证

`python -m unittest discover -s tests -v` 默认只跑轻量校验及素材准备。
运行真实包装 smoke：先安装工程依赖/浏览器，在 PowerShell 设置
`$env:RUN_REMOTION_SMOKE='1'` 后运行同一测试命令；完成后删除该环境变量即可。
CI 仍只有 Windows/Ubuntu 两个任务。仅渲染工程、相关脚本、测试或工作流变化时启用
短渲染测试，纯文档变化不下载 Node 依赖/浏览器；不把技能安装和上游下载放入日常 CI。
