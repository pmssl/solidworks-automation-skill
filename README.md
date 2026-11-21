# SolidWorks Automation Skill

在 Windows 上通过 Python 和 SolidWorks COM 创建、修改和验证原生 CAD 文件。AI 助手从 [SKILL.md](SKILL.md) 读取工作流，可以在本机直接运行 Python CLI 或调用原生脚本，无需 MCP 或常驻 Python 服务。

## 安装与连接

需要 Windows、Python 3.10+ 和本机 SolidWorks。把仓库克隆到支持 Skill 的客户端能发现的位置。以下以 Codex 的项目级目录为例，在目标项目根目录运行：

```powershell
git clone https://github.com/pmssl/solidworks-automation-skill.git .agents/skills/solidworks-automation
Set-Location .agents/skills/solidworks-automation
python -m pip install -r requirements.txt
python scripts/sw_preflight.py
```

在同一个 Windows 用户会话中打开 SolidWorks，然后验证连接。返回 `"document": null` 表示已连上 SolidWorks，当前没有打开文档。

```powershell
python scripts/sw_skill_session.py document
python scripts/sw_skill_session.py --help
```

## 开始建模

在客户端调用 `$solidworks-automation`，说明需要的几何、关键尺寸和输出位置。例如：

> 用 $solidworks-automation 建一个 50 × 30 × 10 mm 的矩形板，保留可编辑的草图和拉伸特征，保存到当前项目的 output 目录。保存前核对草图状态、实体数量和尺寸。

手动调用 CLI 时，可按 `new_part → begin → rectangle → dimension / auto_define → finish → extrude → model_state → save_part` 执行。每条命令返回 JSON。逐步操作使用 `begin` 返回的 `session_id`，会话记录写入 Skill 目录的 `.runtime/solidworks-sessions/`。SolidWorks 重启后需重新开始会话。完整的 PowerShell 示例和保存命令见[原生参数化指南](references/parametric-workflow.md#跨项目使用逐步-cli)。

| 任务 | 入口 |
|---|---|
| 原生草图、尺寸、约束、拉伸、旋转、扫描、放样 | [分步 Python CLI](scripts/sw_skill_session.py) |
| 孔槽、曲面、配置和零件导出 | [原生脚本索引](references/native-capability-catalog.md) |
| 核对孔径、孔轴和沉孔分段 | CLI 的 `measure_geometry`，或 [审查脚本](scripts/sw_review.py) |
| 查看已验证和试点能力 | [能力清单](capabilities.yaml) |

原生零件保存为 `.SLDPRT` 并保留特征树。交付前检查重建状态、实体数量和关键几何。

## 验证与许可

```powershell
python scripts/validate_skill.py
python -m unittest tests.test_native_parametric
```

连接 SolidWorks 后，可运行 `python -m tests.skill_session_live_smoke` 验证跨进程会话、建模和保存。项目使用 [MIT 许可证](LICENSE)。
