# Sakura Desktop Pet — Windows 深度适配版

> 本项目 fork 自 [Rvosy/Sakura](https://github.com/Rvosy/Sakura) v0.9.6，面向 **Windows + NVIDIA GPU** 环境进行了深度适配，并针对单一角色（夜乃桜）进行了沉浸式剧情知识库增强。所有核心架构与工具系统均来自原项目。

Sakura 是一个基于 Python/PySide6 的桌面桌宠 Agent。与传统聊天机器人不同，**她会主动观察你的屏幕、判断你的状态、自己开口说话**。她可以操作浏览器、搜索网页、读写文件、截图分析、设置提醒，一切由 LLM 的工具调用循环驱动。

---

## 本 Fork 的核心特性

### 硬件适配
- **CUDA 加速**：PyTorch 2.12+cu130，支持 RTX 50 系列 GPU
- **TTS 半精度推理**：GPT-SoVITS v2pro NVIDIA50 整合包，自动 FP16
- **Conda 环境管理**：一键激活 `sakura` 虚拟环境

### 双模型架构
- **DeepSeek v4-pro**：主对话模型（1M 上下文）
- **MIMO v2.5**：原生多模态视觉模型，屏幕截图直识别，不降级为文本摘要
- **自适应路由**：画面为主 → MIMO 直接回答；文本对话 → DeepSeek 主力 + MIMO 辅助

### 角色深度
- **原作剧情知识库**：从游戏 `data.pac` 提取桜路线 45 个场景的完整剧本
- **实时 Lore 检索**：对话中关键词命中时自动注入原作记忆
- **叙述段优化**：第一人称视角描写、防日语泄漏、底对齐字幕

### UI 改善
- 气泡框底对齐 + 实时重绘，多行文本始终可见
- 字幕语言守卫，避免日文泄露到中文字幕
- 修复叙述段误转为 TTS 朗读的问题

---

## 环境配置

### 前提

- Windows 10/11 x64
- NVIDIA GPU（RTX 30/40/50 系列，建议 8GB+ VRAM）
- Anaconda/Miniconda

### 第一步：克隆仓库

```powershell
git clone https://github.com/EMTq31206/Sakura_change.git
cd Sakura_change
```

### 第二步：创建 Conda 环境并安装依赖

```powershell
conda create -n sakura python=3.11 -y
conda activate sakura

# 先安装 CUDA 版 PyTorch
pip install torch --index-url https://download.pytorch.org/whl/cu130

# 再安装其余依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
python -m playwright install chromium
```

### 第三步：配置 API Key

复制并编辑 `data/config/api.yaml`（模板见 `data/config/api.yaml.deepseek`）：

```yaml
llm:
  base_url: https://api.deepseek.com
  api_key: 你的DeepSeek Key
  model: deepseek-v4-pro
  timeout_seconds: 120

vision:
  enabled: true
  base_url: https://api.xiaomimimo.com/v1
  api_key: 你的MIMO Key
  model: mimo-v2.5
  timeout_seconds: 60

tts:
  provider: gpt-sovits
  enabled: true
  gpt_sovits:
    api_url: http://127.0.0.1:9880/tts
    precision_mode: auto
```

### 第四步：安装 TTS 整合包

启动后在设置页 → TTS → 一键下载 TTS 整合包，选择 **GPT-SoVITS v2pro NVIDIA 50 系**。

### 第五步：启动

```powershell
conda activate sakura
python main.py
```

或直接双击 `start.bat`（已内置 conda 激活）。

---

## 相对原项目的改动

### 新增模块
| 文件 | 说明 |
|------|------|
| `app/agent/character_lore.py` | 角色剧情知识库，关键词索引 + 实时记忆注入 |
| `app/agent/web_search.py` | CJK 字符级搜索过滤 |
| `app/llm/chinese_text.py` | 简体中文强制转换 |

### 核心修改
| 文件 | 改动 |
|------|------|
| `app/voice/tts.py` | CUDA 设备自动 FP16 推理（原仅 MPS） |
| `app/storage/visual_observation.py` | Vision API max_tokens + detail=high + 画面布局字段 |
| `app/core/chat_pipeline.py` | 屏幕观察 → MIMO 直答路由；Lore 检索注入 |
| `app/llm/chat_reply.py` | kana_ratio 语言防御；叙述段静默降级 |
| `app/llm/prompts/blocks.py` | zh 必填守卫 + 复读禁止规则 |
| `app/ui/pet_window.py` | AlignBottom 字幕对齐 |
| `app/ui/subtitle_controller.py` | repaint 实时重绘 |
| `characters/sakura/card.md` | 155 行 → 282 行：14 个世界观条目 + 7 幕完整剧情 + 15 条记忆清单 |
| `characters/sakura/lore.md` | 1.8MB：桜路线 + Grand Route 原文剧本 |
| `start.bat` | Conda 环境自动激活 |
| `requirements.txt` | 添加 CUDA 安装指引 |
| `.gitignore` | 排除 API 备份文件 |

### 未跟进的上游特性
本项目停留在 v0.9.6 基础上进行角色沉浸向迭代，**未跟进上游 0.9.7-dev** 的架构硬化（协作取消、启动自检、原子写入、交互 ID、运行时事件系统）、UI 现代化（气泡自动隐藏、输入栏动画、窗口背景模糊）、平台集成（开机自启）、TTS 稳定性增强等。如需这些能力，建议使用上游版本。

---

## 技术文档

- [Sakura 技术讲解 README](docs/TECHNICAL_README.md)
- [Sakura 插件 SDK 文档](docs/SAKURA_PLUGIN_SDK.md)

## 致谢

感谢 [Rvosy](https://github.com/Rvosy) 开源的 Sakura 项目，本项目的所有核心架构、角色框架、工具系统和插件机制均源于此。
