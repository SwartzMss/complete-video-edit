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

这是一套执行规范，不是无需审查即可自动完成剪辑的软件。照片动画的设计规则在 `skills/complete-video-edit/references/visual-design.md`，具体剪点和动画工程按每条素材建立。

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

## 仓库范围

保存 Skill、参考规则、转写脚本和依赖锁定文件。家庭照片、原片、成片、转写内容、模型、缓存、虚拟环境与账号凭据不纳入版本管理。

本次更新加入默认无字幕装饰、与讲述同步的照片展示、双照片入场/逐张放大和局部预览规范。FFmpeg 与 Remotion 可按任务需要选择，不固定工具或时长。
