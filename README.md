# 完整内容精剪 · complete-video-edit

用于 Codex 的个人视频剪辑 Skill，配套本地语音转写入口。

## 默认工作方式

- 保留全部独立信息、原始顺序、重要动作与原声。
- 只清理无意义的重复、卡顿和长空白，不默认追求一分钟。
- 默认不添加字幕、顶部章节、标题底板或装饰星星。
- ASR 用于内部理解；识别文字是初稿，不能直接当作已校对字幕烧录。
- 按讲述位置插入用户提供的照片，保持原声连续。
- 多图可一起入场，再逐张移到中央放大，最后返回讲话画面。
- 局部修改交付带前后衔接的短预览和完整视频。

这是一套执行规范及配套工具，不是无需审查即可自动完成剪辑的软件。基础精剪由经审查的计划驱动固定工具执行；照片动画的设计规则在 `skills/complete-video-edit/references/visual-design.md`，具体剪点和动画工程仍按每条素材建立。

## 安装 Skill

将整个 `skills/complete-video-edit` 文件夹复制到 Codex 的 skills 目录（通常为 `~/.codex/skills`）。该目录包含脚本、依赖锁定文件和独立调用说明，安装后不依赖仓库根目录，可移走仓库。已有同名 Skill 时先比较内容并保留本机运行环境说明。

调用示例：

> 使用 $complete-video-edit 精剪这条视频，保留完整内容；在讲到拍照时加入我提供的照片，做共同入场、逐张放大的动画。

## 本地转写入口

进入安装后的 Skill 目录，使用 Python 3.12 和 uv 创建独立环境（也可进入仓库中的 `skills/complete-video-edit`）：

```powershell
Set-Location "$env:USERPROFILE\.codex\skills\complete-video-edit"
uv venv --python 3.12 .venv
uv pip sync --python .venv/Scripts/python.exe requirements.lock.txt
& .venv/Scripts/python.exe scripts/transcribe.py 'C:\素材\原片.mp4' --output 'C:\素材\转写-v1' --device cpu
```

GPU 示例：增加 `--device cuda --gpu-libs 'C:\路径\CUDA-DLL目录'`，该目录须有兼容的 CUDA 12/cuDNN 9 库。已在系统可用时可省略 `--gpu-libs`。首次使用模型需下载；默认 `small`，模型缓存到 `scripts/models`。输出目录必须不存在，以保护已有稿件。

检测到语音时生成 `transcript.draft.txt`、`subtitles.draft.srt` 和 `transcript.json`。TXT 内也标明待校对；SRT 只用文件名标识，不插入会显示的免责声明。旧文件名 `transcript.txt`、`subtitles.srt` 不再生成，消费脚本需更新。

未检出语音时正常退出，仅保存 `transcript.json`（`status=no_speech_detected`），继续审查画面、动作及现场声；怀疑轻声对白被过滤时可用 `--no-vad` 输出到新目录复核。解码失败则非零退出并记录 `decode_failed`，不能当作无语音成功。模型或推理异常仍是非零失败，不能据此认定无对白。

脚本采用可配置路径。依赖快照来自已验证环境，不自动升级；PyAV 16.0.1 与 Faster-Whisper 1.2.1 的实际组合已测试过。完整操作说明随 Skill 安装，见 `references/local-runtime.md`。

## 统一基础精剪

单原片、原顺序、正常速度的基础精剪，先生成 `edit-plan.json`，只列出经审查的删除区间；未列出的内容默认保留。然后在 Skill 目录运行：

```powershell
python scripts/edit.py check 'C:\素材\edit-plan.json'
python scripts/edit.py render 'C:\素材\edit-plan.json' --output 'C:\素材\精剪-v1'
python scripts/edit.py verify 'C:\素材\精剪-v1'
```

`render` 自动完成校验、渲染与技术验收，输出目录必须是新目录。保留计划、时间映射、输入指纹、实际命令和验收报告；通过后才发布成片。需要 Python 3.10+ 和 FFmpeg/FFprobe，无新增 Python 依赖。格式、帧边界规则和首版素材限制见 [剪辑计划说明](skills/complete-video-edit/references/edit-plan.md)。

如果提示 FFprobe 没有报告 `pix_fmt`，通常是桌面应用附带的精简 FFprobe 没有该素材的解码器；换用完整 FFprobe 或先转成受支持的 H.264 素材，不要跳过探测校验。

**对现有使用的影响：** 转写、下载命令及视觉配方保持兼容；调用 Skill 的方式不变。基础精剪新增可复用执行路径，不自动迁移旧工程，也不修改已安装的 Skill。更新本机时复制完整 Skill 目录，并保留本机环境说明。技术验收不能替代内容及剪口听辨检查。

## 可选 Remotion 包装

可选复杂双照片包装使用独立 `visual-plan.json` 和随 Skill 分发的 Remotion 模板；支持共同入场、逐张放大、局部预览与关键帧检查。完整输出复制精剪母版原声音轨。基础精剪与旧命令不变，只有需要动画时才准备 Node/浏览器依赖。Windows 安装与完整示例见 [Remotion 集成说明](skills/complete-video-edit/references/remotion-integration.md)。不引入 submodule，不复制官方技能内容。

## 素材清单与可用性检查

在 Skill 目录执行 `python scripts/check_assets.py`，或加 `--json` 获取机器可读报告、加 `--decode` 抽样解码开头一秒。无需额外 Python 依赖；缺少 FFprobe 会提示未探测，不会误报素材损坏。

安装时保留完整 `assets/` 目录。彩条视频/蜂鸣音随仓库分发，熊出没片尾仅有清单，本地视频需单独准备；manifest 存在不代表文件已发布。文件、哈希、媒体工具及再分发授权分别报告，不自动下载或上传素材。字段约定、状态和退出码见 [素材清单说明](skills/complete-video-edit/references/asset-manifests.md)。现有剪辑、转写、下载及动画命令不变。

## 开发验证

```text
python -m unittest discover -s tests -v
```

FFmpeg 集成测试使用临时生成的颜色/音调素材，核对实际保留内容、音画时序及完整解码；缺少 FFmpeg/FFprobe 时明确跳过。CI 仍只有 Ubuntu 和 Windows 两个任务；仅相关代码变化时安装可选 Remotion 运行环境并进行短包装渲染，避免普通文档改动触发昂贵检查。

## 仓库范围

保存 Skill、参考规则、转写与剪辑脚本、示例计划和依赖锁定文件。家庭照片、原片、成片、个人剪辑记录、转写内容、模型、缓存、虚拟环境与账号凭据不纳入版本管理。

本次更新加入默认无字幕装饰、与讲述同步的照片展示、双照片入场/逐张放大和局部预览规范。FFmpeg 与 Remotion 可按任务需要选择，不固定工具或时长。

## 可选抖音下载

支持将用户提供的抖音链接或分享文案保存为本地参考视频。安装与失败处理见 `skills/complete-video-edit/references/douyin-download.md`，调用入口为 `scripts/download_douyin.py`。第三方后端按固定版本单独下载，使用独立环境；不会混入 ASR 依赖。只有媒体探测、时长与完整解码检查通过才报告成功。

## 可选卡通片尾

加入熊出没式“彩色画面缩小转黑白 + 右侧滚动片尾文字”的制作配方，见 `skills/complete-video-edit/references/cartoon-outro.md`。用户现已选择原模板替换：本机 Skill 保存有台标绿幕视频，保留名单、动画与音轨，只替换绿色窗口。GitHub 仅含来源、操作规则与 assets/boonie-bears-outro/manifest.json；迁移机器须单独复制该目录内的视频或按来源重新获取。重建设计仅在用户明确要求时使用。
