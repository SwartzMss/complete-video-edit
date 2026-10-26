# 本地运行环境适配

此仓库版本不保存个人主机绝对路径。执行任务时优先检查用户已有独立转写环境、FFmpeg/FFprobe 和 Remotion 工程，避免修改无关环境。

本 Skill 自带 `scripts/transcribe.py`、`scripts/edit.py`、`scripts/editing/` 和 `requirements.lock.txt`，路径均相对于 Skill 根目录（本文件的父目录的父目录），不需要仓库根目录。把完整 Skill 目录复制到另一台机器即可保留执行入口；Python、uv、依赖和模型需在该机器上准备。

基础精剪工具仅依赖 Python 标准库与 FFmpeg/FFprobe，不需要安装转写依赖或下载模型。命令、格式和明确的素材支持范围见 [剪辑计划与执行工具](edit-plan.md)。现有转写/下载入口不变；更新 Skill 时需连同 `scripts/editing/` 子目录一起复制，保留本机环境记录。程序不会自动更新安装目录或系统环境。

在安装后的 Skill 根目录运行：

```powershell
Set-Location "$env:USERPROFILE\.codex\skills\complete-video-edit"
uv venv --python 3.12 .venv
uv pip sync --python .venv/Scripts/python.exe requirements.lock.txt
& .venv/Scripts/python.exe scripts/transcribe.py 'C:\素材\原片.mp4' --output 'C:\素材\转写-v1' --device cpu
```

如果 Codex 使用自定义 skills 位置，应使用实际 SKILL.md 所在目录，而非猜测默认目录。输出目录必须不存在；默认模型 small，首次使用需要下载，缓存于脚本旁 `models`。检测到语音后输出 `transcript.draft.txt`、`subtitles.draft.srt`、`transcript.json`，这些是待校对自动稿。TXT 有初稿说明，SRT 不含会显示到视频的免责声明。旧版消费程序应迁移到 `.draft` 文件名。

## 无对白和错误分支

- `status=transcribed`：正常退出，生成文字、字幕和词时间戳；`review_status=automatic_unreviewed`。
- `status=no_speech_detected`：正常退出，只保存 JSON 状态及后续动作，不生成空字幕。继续画面、动作、展示过程和现场声审查；不能据此删内容或认定整条任务失败。怀疑轻声被 VAD 漏检时，用同一输入加 `--no-vad` 输出到新目录，再复核结果，避免静音幻觉。
- `status=decode_failed`：非零退出，JSON 记录错误；排查格式、损坏和音轨是否存在。确认原片没有音轨时走纯视觉审查，不把它伪装成成功识别。
- 模型加载/推理/依赖异常：非零退出，属于工具故障，不属于“无语音”；先排查，不吞掉错误。

优先使用 Python 3.12 独立环境。已验证组合为 Faster-Whisper 1.2.1、PyAV 16.0.1；PyAV 19.0.2 曾因 `metadata_errors` 参数变化导致解码失败，不应无理由解除锁定。

CPU 可使用 `--device cpu`。CUDA 运行需要匹配的运行库；`--gpu-libs` 可指定本机 DLL 目录，仅在当前进程加载，不修改全局 PATH。检查模型加载和真实素材转写都成功后再报告可用。

FFmpeg 的存在不代表支持全部滤镜；分别检查图像解码、ASS、合成和音频能力。插件启动错误与媒体程序本体错误应分开诊断。不要为了兼容性修复盲目重装系统 Python。

基础精剪还需要 FFprobe 能返回视频流的 `pix_fmt`。桌面应用附带的精简 FFprobe
可能没有某些编码的解码器（例如 FFV1），遇到这类素材会缺少该字段；这是探测
能力限制，不是素材一定损坏。换用完整 FFprobe，或先把素材转成受支持的 H.264
、方形像素、8-bit 格式；工具会在错误信息中说明原因。

照片动画与实际项目脚本保存于用户的本地项目中；创建独立输出版本，保留原片，勿提交个人媒体或转写到代码仓库。

可选双照片模板随 Skill 的 `remotion/` 目录分发，只有使用时才准备 Node 22+、`npm ci` 和渲染浏览器。完整 Windows 命令、官方技能发现、缺失依赖处理与预览方式见 [Remotion 集成流程](remotion-integration.md)。`scripts/visual.py prepare` 只使用 Python/FFmpeg；渲染才加载 Node 工程，不改变原有转写与基础精剪环境。
