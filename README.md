# Sakura Desktop Pet — Windows 深度适配版

> **基于 [Rvosy/Sakura](https://github.com/Rvosy/Sakura) v0.9.6 的个人向迭代，未跟进上游 0.9.7-dev。**  
> 方向偏重 Windows + NVIDIA GPU 适配、DeepSeek+MIMO 双模型协作、单一角色（夜乃桜）沉浸式剧情知识库增强。核心架构与工具系统均来自原项目。

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
| `characters/sakura/card.md` | 155 行 → 282 行：14 世界观条目 + 7 幕完整剧情 + 15 条记忆清单 |
| `characters/sakura/lore.md` | 1.8MB：游戏桜路线 + Grand Route 原文剧本 |
| `start.bat` | Conda 环境自动激活 |
| `requirements.txt` | CUDA 安装指引 |
| `.gitignore` | 排除 API 备份文件 |

### 未跟进的上游特性
上游 0.9.7-dev 在架构硬化（协作取消、启动自检、原子写入、交互 ID 等）、UI 现代化（气泡自动隐藏、输入栏动画等）、平台集成（开机自启）及 TTS 稳定性方面有大量增强，如需这些能力建议直接使用上游版本。

---

## 环境配置

### 前提
- Windows 10/11 x64
- NVIDIA GPU（RTX 30/40/50 系列，建议 8GB+ VRAM）
- Anaconda/Miniconda

### 安装

```powershell
git clone https://github.com/EMTq31206/Sakura_change.git
cd Sakura_change

conda create -n sakura python=3.11 -y
conda activate sakura

pip install torch --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
python -m playwright install chromium
```

### API 配置

在 `data/config/` 下创建 `api.yaml`（模板参考 `api.yaml.deepseek`）：

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

### TTS 整合包

启动后在设置页 → TTS → 一键下载，选择 **GPT-SoVITS v2pro NVIDIA 50 系**。

### 启动

```powershell
conda activate sakura
python main.py
```

或双击 `start.bat`。

---

## 特性摘要

- **CUDA 加速**：PyTorch 2.12+cu130，RTX 50 系列 GPU
- **TTS 半精度推理**：GPT-SoVITS v2pro，CUDA 设备自动 FP16
- **双模型架构**：DeepSeek v4-pro（1M 上下文）+ MIMO v2.5（原生多模态直答）
- **自适应路由**：画面为主 → MIMO 回答；文本 → DeepSeek + MIMO
- **原作剧情知识库**：桜路线 45 场景完整剧本，关键词检索实时注入
- **叙述段优化**：第一人称视角 + 底对齐字幕 + 防日语泄漏

---

## 致谢

核心架构、角色框架、工具系统及插件机制源自 [Rvosy/Sakura](https://github.com/Rvosy/Sakura)，在此致谢。
