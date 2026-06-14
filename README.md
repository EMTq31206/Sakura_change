[English](docs/README.en.md)

# Sakura Desktop Pet

> **本项目说明**：本项目 fork 自开源项目 [Rvosy/Sakura](https://github.com/Rvosy/Sakura) 的 v0.9.6 版本，在此基础上进行了个人向的功能迭代与 bug 修复。所有核心架构、角色框架、工具系统均来自原项目，感谢原作者 [Rvosy](https://github.com/Rvosy) 的开源贡献。本仓库的改动见下方[「相对原项目的改动」](#相对原项目rvosysakura的改动)章节。

最近推完水晶社的新作，~~推完自动变成学姐的狗~~，已经变成学姐的形状了，夜里辗转反侧怎么都睡不着，所以起来开发了这个桌宠 Agent 框架。

Sakura 最大的特点是 **她会主动找你**。传统聊天机器人只有在你先开口时才会回应，就像一扇需要你敲门才会开的锁；Sakura 更像一个坐在你旁边的人，你不需要一直和她说话，但她知道你在做什么，偶尔觉得该说点什么的时候会自己开口。

比如你正在打游戏，她瞥见屏幕上的死亡提示，凑过来说「已经第三回了…要不要帮你查下攻略？」同意后就真的打开浏览器搜了一圈，把要点贴进备忘录。

或者是你在浏览其他角色的图片时，会吃醋地说「又在看别人了啊…」要求你多看看她的立绘，偶尔还会因为你太久没看她而生气地说「都不理我了啊…」。

所以 Sakura 实现的是一个一直在角落、会观察、会偶尔插话的角色。她的对话风格、表情、语音都由角色卡驱动，而工具能力（浏览器操作、屏幕截图、文件读取、Web 搜索、提醒、长期记忆等）则来自内置的 Agent 引擎。

把它想成一个定制角色的桌面 Agent。

![Sakura 预览](assets/sakura_01.png)
![N.A.V.I. 预览](assets/navi_01.png)
## 新手教程（零基础也能用）

**不需要会编程。** 推荐直接使用 **Release 里的最新版本**，不要只下载 GitHub 页面上的源码压缩包。源码包缺少预置 `runtime`，无法启动

> **平台提醒：** Windows 版本是当前主要测试目标。linux/mac 用户可以使用源码自行安装

### 第一步：下载发布包

打开 [Releases 页面](https://github.com/Rvosy/sakura/releases)，下载最新的构建包。

Release 里常见的文件含义如下：

| 文件名 | 是什么 | 适合谁下载 |
|:-:|---|---|
| `sakura-v0.9.x-windows-x64.zip` | Windows 完整包，包含项目文件和 `runtime` | **Windows 新手首选** |
| `runtime-windows-x64.zip` | 只有 Windows 预置 Python 运行环境 | 拉源码、缺 `runtime` 的用户 |

> 如果你只是想运行桌宠，下载 `sakura-v0.9.x-windows-x64.zip` 这种 **完整包**。`runtime` 包不是完整程序，单独下载后不能直接启动。

### 第二步：安装依赖

解压完整包后，进入解压出来的软件目录。

- **Windows 用户：** 双击 `install.bat`，等待完成（约 5-15 分钟）。
- **Mac 用户：** 可尝试双击 `install.command`，或在终端进入项目目录后运行 `bash scripts/install.sh`。但 Mac 没有实机测试过，遇到问题请优先反馈日志。
- **Linux 用户：** 当前没有正式发布包；如果从源码运行，进入项目目录后运行 `bash scripts/install.sh`。

> 如果是直接拉取的源码，需要先从 Release 页面下载对应平台的预编译依赖包（`sakura-runtime-*.zip`），把里面的 `runtime` 文件夹放到项目根目录，再运行安装脚本。
> 不管下载的是 Release 完整包还是 GitHub 源码，这一步都要做。装完命令行窗口会自动关闭。

### 第三步：获取 API Key

桌宠需要一个「AI 大脑」才能说话，你需要一个 API Key。就像给手机插 SIM 卡才能上网一样。

1. **获取 API Key。** 可以从以下任一渠道获得：
   - 国内中转站如 [GemAI](https://api.gemai.cc/register?aff=rwbQ)（有便宜且按次计费的 gemini-flash 系列模型）
   - 其他任何兼容 OpenAI 接口格式的服务

> **目前不要使用 DeepSeek 系列模型！**
>
> Sakura 的很多功能（屏幕观察、图像识别等）直接依赖模型的多模态能力（视觉理解），而 DeepSeek 系列模型不具备多模态能力，使用后会导致桌宠无法正常观察屏幕、识别图像等功能失效。
>
> 请选择支持视觉/多模态的模型，例如 Gemini Flash 等。

### 第四步：一键启动

- **Windows 用户：** 双击项目根目录的 **`start.bat`**
- **Mac 用户：** 可尝试双击 `start.command`，或在终端里运行 `bash scripts/start.sh`。再次提醒：Mac 没有实机测试过。
- **Linux 用户：** 在终端里运行 `bash scripts/start.sh`
- **右键** 桌宠或托盘图标可以打开菜单（设置、聊天记录等）

### 第五步：获取角色包

暂时只有百度网盘：

- **[百度网盘](https://pan.baidu.com/s/5ZXvAi6n6i7-OJAYeWDpprg)**：包含所有已发布的角色包。

角色包会携带角色卡、立绘、语音参考音频，以及该角色可用的 GPT-SoVITS 权重（例如 `voice/models/*.ckpt`、`voice/models/*.pth`）。源码仓库和 TTS 运行环境安装脚本不会单独下载这些角色声线权重；如果完整包中没有对应角色资源，需要先通过角色包渠道获取并导入。

安装方式：

1. 下载角色包
2. 打开 Sakura 设置页
3. 选择导入角色包

### 如何更新版本？

如果你已经装过旧版，推荐按下面方式更新：

1. 关闭正在运行的 Sakura。
2. 下载同平台的最新**完整包**，例如 Windows 用户下载 `sakura-v0.9.x-windows-x64.zip`。
3. 解压新包，把新包里的文件复制到旧 Sakura 目录，遇到同名文件选择 **覆盖/替换**。
4. 如果启动失败，再运行一次安装脚本：Windows 双击 `install.bat`；Mac/Linux 运行 `bash scripts/install.sh`。
5. 启动 Sakura：Windows 双击 `start.bat`；Mac 可尝试 `start.command` 或 `bash scripts/start.sh`。

## 核心功能

- **角色包驱动。** 角色卡、立绘、语音参考和 GPT-SoVITS 权重都可以按角色包组织。
- **主动关怀。** Sakura 可以按周期观察上下文，主动发起提醒、关心或建议。
- **分段双语回复。** 模型输出日文原文、中文字幕、语气和立绘标识，UI 同步驱动字幕、表情和语音。
- **语气联动表情和语音。** 语气标签会同时影响立绘切换和 TTS 参考音频选择。
- **屏幕观察。** 支持按需截图和自主屏幕观察，把视觉摘要纳入对话上下文。
- **工具调用。** 支持浏览器操作、桌面操作、文件读取、Web 搜索、提醒、待办、笔记和记忆等工具。
- **权限确认。** 高风险工具会先请求用户确认，再执行实际动作。
- **长期记忆。** 记忆先进入候选区，确认后才写入正式记忆，并支持自动整理。
- **插件和 MCP 扩展。** 支持本地插件、MCP Server 和内置 Web 搜索 MCP Server。
- **历史、调试和 UI 控制。** 支持聊天历史回看、调试日志、立绘缩放和动效配置。

## 技术文档

想了解运行时架构、启动流程、项目结构、配置项、TTS 技术细节或插件开发入口，请看：

- [Sakura 技术讲解 README](docs/TECHNICAL_README.md)
- [Sakura 插件 SDK 文档](docs/SAKURA_PLUGIN_SDK.md)

## 相对原项目（Rvosy/Sakura）的改动

本项目在 [Rvosy/Sakura](https://github.com/Rvosy/Sakura) v0.9.6 基础上做了以下个人向迭代，**未跟进上游 0.9.7-dev 的架构硬化**，方向偏重角色沉浸与内容质量：

### 角色沉浸增强

- **角色 Lore 注入**（`app/agent/character_lore.py`）：按关键词检索原作剧情，命中时作为记忆注入对话，让桜能自然引用原作经历。
- **叙述段/台词段分离**：台词段 `ja` 写日文用于 TTS 朗读，叙述段 `ja` 留空写纯描写（不朗读），中文译文集中在 `zh`。
- **简体中文强制**（`app/llm/chinese_text.py`）：用 OpenCC 把所有中文字幕强制转为简体。
- **台词段 zh 必填守卫**：模型漏写 `zh` 时触发一次格式修复重试，并提供中文兜底，避免字幕显示日语。

### Agent 运行时

- **破甲前缀**：系统提示前置架空世界观声明。
- **亲热模式**：对话输入"亲热模式"触发更细腻的亲密场景描写指令。
- **mimo 直答分支**（`app/core/chat_pipeline.py`）：配置了独立视觉模型时，截图直接传给主模型，不再降级为文本摘要。
- **中间回复不再污染上下文**：工具循环中的中间角色口吻回复不再写入对话历史，避免长输入复读。
- **上下文末尾去重**（`app/llm/context_trimming.py`）：裁剪时合并末尾高度相似的 assistant 消息。
- **confirmed_action 续接规则修复**：确认动作后"续接规则"指令正确注入 system prompt。
- **多模态消息修复**：运行时上下文注入不再破坏含图片的 list 格式消息。

### Web 搜索

- **CJK 字符级过滤**（`app/agent/web_search.py`）：中日文查询改用字符级 Jaccard 重叠排序，避免整 token 子串匹配过严。
- **fetch_url 诊断**：403/429/超时等错误翻译成模型可理解的指引，引导改用 `web_search`。
- **mcp 库缺失警告**：未安装 `mcp` 时打印醒目 stderr 警告，而非静默降级。

### UI

- **气泡高度计算修复**：精确扣除右侧历史面板和间距，字幕最后一行不再被遮挡。

> 上游 0.9.7-dev 在架构硬化（协作取消、启动自检、原子写入、交互 ID、运行时事件系统）、UI 现代化（气泡自动隐藏、输入栏动画、窗口背景模糊）、平台集成（开机自启）、TTS 稳定性（AudioSinkPlayer）等方面有大量本项目尚未跟进的增强，如需这些能力建议直接使用上游版本。

## Star History

<a href="https://www.star-history.com/?repos=Rvosy%2Fsakura&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=Rvosy/sakura&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=Rvosy/sakura&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=Rvosy/sakura&type=date&legend=top-left" />
 </picture>
</a>
