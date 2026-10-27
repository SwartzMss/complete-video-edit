# 素材清单与本机可用性检查

`assets/` 是随 Skill 复制的资源目录。清单存在只代表资源已登记，不代表媒体已随 GitHub 发布。彩条视频和蜂鸣音随仓库分发；熊出没片尾只分发清单，视频保存在用户本机。安装时保留仓库跟踪的整个素材目录；更新已安装 Skill 时保留本机专用视频，不用删除目标目录的方式同步。

## 运行

Python 3.10+，无第三方 Python 依赖。在安装后的 Skill 目录运行（Windows PowerShell 同样适用）：

```powershell
python scripts/check_assets.py
python scripts/check_assets.py --json
python scripts/check_assets.py --decode --json
python scripts/check_assets.py --ffprobe 'C:\工具\ffprobe.exe' --ffmpeg 'C:\工具\ffmpeg.exe'
```

默认扫描脚本所在 Skill 的 `assets/**/manifest.json`，与当前工作目录无关。可用 `--root 'C:\素材清单'` 扫描其他素材根目录。扫描顺序固定，以 UTF-8 输出，不写报告文件；如需保存 JSON，可由调用方重定向到一个新的报告文件。脚本不修改素材或清单，不安装依赖、不下载、不上传。来源 URL 仅显示，不访问；媒体工具限制为本地 file/pipe 协议，不允许媒体引用触发网络下载。

默认检查结构、文件可读性、已配置的 SHA-256，并在 FFprobe 存在时探测流信息。`--decode` 额外用 FFmpeg 解码开头至多一秒，30 秒超时；它不是整片完整性校验。模板文件只检查文件/哈希/依赖，不当成媒体探测。

## Manifest v1 规则

标准库验证器 `scripts/asset_inventory.py` 的 `load_manifest()` 是可执行验证规则；检查命令对每份清单执行它。不需要安装 JSON Schema 验证库。JSON 必须是对象，不允许重复键或未知字段。无版本的历史清单已在仓库迁移；用户自行维护的旧清单需按下列结构迁移，工具不会自动重写。

顶层字段全部必填：

| 字段 | 约定 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `asset_id` | 扫描范围内唯一；小写字母、数字，以 `-` 或 `_` 分隔；例如 `tv-color-bars` |
| `name` / `description` | 非空名称与用途描述 |
| `kind` | `video`、`audio`、`image`、`template` 或 `bundle` |
| `usage` | 非空字符串数组，登记用户选择的编辑用途，不是法律授权 |
| `files` | 非空文件数组；配套视频/音效各自有记录 |

每项 `files[]` 的必填字段：

| 字段 | 约定 |
| --- | --- |
| `file_id` | 包内唯一，字符规则同 `asset_id` |
| `path` | 相对 **manifest 所在目录** 的文件路径，统一 `/` 分隔；禁止绝对路径、盘符、URL、空段、`.`、`..`、反斜杠和逃逸目录的符号链接；同一文件不能重复登记 |
| `kind` | `video`、`audio`、`image` 或 `template` |
| `role` | 非空角色说明，例如 `transition`、`synchronized_sound`、`outro` |
| `storage` | `bundled`（应随 Skill 分发）或 `local_only`（需用户本地准备） |
| `source` | `url` 为 HTTP(S) 来源链接或 `null`；`description` 为非空来源说明。可选 `interval_seconds: [start, end]`（0 ≤ start < end）与 `crop`（非空裁切记录） |
| `rights` | 必填 `license`、`redistribution`、`notes`；`license`、`notes` 为非空文本，`redistribution` 只能为 `allowed`、`prohibited`、`unknown`；无依据时许可证写 `unknown` |
| `requires` | 可为空的可执行程序名数组，仅支持 `ffmpeg`、`ffprobe`、`node`；只查找程序，不执行清单中的命令或安装包 |

可选文件字段：

- `sha256`：64 位小写十六进制字符串。省略表示未配置指纹，不能声称已确认文件身份。
- `notes`：字符串数组，保留同步音效、听辨状态等额外记录。
- `metadata`：可包含正数 `duration_seconds`；正整数 `width`、`height`、`sample_rate`、`channels`；正有理数形式的字符串 `fps`；非空 `video_codec`、`audio_codec`；布尔 `has_alpha`、`has_audio`；有限数值 `peak_dbfs`。未知项省略，不能用 `false` 代替未知。

`metadata` 是登记值；探测结果另存于报告的 `probe.streams` / `probe.format`，当前不会逐项对比登记值，也不会修改清单。透明通道、浏览器支持及依赖版本/编解码器能力不从可执行文件存在与否推断。

每个文件分别登记来源和授权；不能因为音效是本地合成、视频已入库或用户认可某种剪辑，就自动把再分发状态改成 `allowed`。检查器只展示声明，不作授权判定，不因授权未知阻止本地技术检查。

## JSON 报告与状态

报告顶层为 `schema_version: 1`、`root`、`tools`、`assets`、`issues`、`summary`。`tools` 给出找到的程序路径或 `null`；`assets` 保留包信息及逐文件检查结果。一个坏清单不会隐藏其他包。错误与警告使用 `issues[]` 中的 `code`、`severity`、`message`，调用方应依赖 `code` 而非解析提示文本。

| 检查字段 | 状态 |
| --- | --- |
| `manifest_status` | `valid` / `invalid` |
| `existence` | `present` / `missing` / `unreadable` / `not_checked` |
| `hash.status` | `matched` / `mismatch` / `not_configured` / `not_checked` |
| `probe.status` | `passed` / `failed` / `tool_missing` / `not_applicable` / `not_checked` |
| `decode.status` | `sample_passed` / `failed` / `tool_missing` / `not_applicable` / `not_checked` |
| `dependencies` | 每个声明的程序对应 `found` / `missing`，不表示版本或渲染器完整可用 |
| `rights.redistribution` | 原清单的 `allowed` / `prohibited` / `unknown` |
| `browser_preview` / `render` | 当前均为 `not_checked`，不能用 FFprobe 成功或抽样解码替代实际播放/渲染验收 |

机器可读问题代码：

- 错误：`inventory_failed`（扫描根目录不存在/为空或无法扫描）、`manifest_invalid`、`bundled_file_missing`、`file_unreadable`、`hash_mismatch`、`probe_failed`、`decode_failed`。
- 警告：`local_file_missing`、`dependency_missing`、`probe_tool_missing`、`decode_tool_missing`、`redistribution_unknown`、`redistribution_prohibited`。

文件缺失或不可读时后续媒体检查为 `not_checked`；指纹不符也跳过媒体检查。FFprobe 缺失明确记录 `tool_missing`，不报媒体损坏；使用 `--decode` 时仍可独立尝试 FFmpeg 抽样解码。

退出码 `0` 表示没有错误，**不代表所有素材就绪或允许公开分发**，仍需查看警告和检查状态；`1` 表示至少一个错误；`2` 表示 CLI 参数错误。熊出没片尾现为 bundled 素材；完整安装应包含视频，缺失会报告 bundled_file_missing 并返回失败。local_only 类型仍可用于其他需本地准备的素材，缺失时只告警。准备片尾时向用户说明缺失文件和来源，按用户明确指示复制或获取素材，不自动下载。

此工具独立于精剪计划和 Remotion，未改变二者的验收或执行命令。未来 UI 可消费 JSON，但当前不包含 UI、数据库、服务或自动渲染器。
