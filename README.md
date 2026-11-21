# SolidWorks Automation Skill

在 Windows 上通过 Python 和 SolidWorks COM 创建、修改和验证原生 CAD 文件。AI 助手从 [SKILL.md](SKILL.md) 读取工作流，并编写 Python 脚本直接调用原生能力库。

## 安装与连接

需要 Windows、Python 3.10+ 和本机 SolidWorks。把仓库克隆到支持 Skill 的客户端能发现的位置。以下以 Codex 的项目级目录为例，在目标项目根目录运行：

```powershell
git clone https://github.com/pmssl/solidworks-automation-skill.git .agents/skills/solidworks-automation
Set-Location .agents/skills/solidworks-automation
python -m pip install -r requirements.txt
python scripts/sw_preflight.py
```

在同一个 Windows 用户会话中打开 SolidWorks，然后验证连接。返回字典中 `document` 为 `None` 表示已连接 SolidWorks，当前没有打开文档。

```powershell
python -c "from scripts.sw_skill_session import run_action; print(run_action('document'))"
```

## 开始建模

在客户端调用 `$solidworks-automation`，说明需要的几何、关键尺寸和输出位置。例如：

> 用 $solidworks-automation 建一个 50 × 30 × 10 mm 的矩形板，保留可编辑的草图和拉伸特征，保存到当前项目的 output 目录。保存前核对草图状态、实体数量和尺寸。

在 Python 脚本中直接导入需要的建模函数。使用 `NativeParametric` 可串联草图、尺寸、特征和验收步骤。跨进程续接同一草图时，用 `run_action()` 传递 `session_id`。调用示例见[原生参数化指南](references/parametric-workflow.md#在-python-脚本中调用)。

| 任务 | 入口 |
|---|---|
| 原生草图、尺寸、约束、拉伸、旋转、扫描、放样 | [原生建模函数](scripts/sw_part.py)与 [Python 会话类](scripts/sw_native_parametric.py) |
| 孔槽、曲面、配置和零件导出 | [原生脚本索引](references/native-capability-catalog.md) |
| 核对孔径、孔轴和沉孔分段 | [`collect_geometry_measurements(model)`](scripts/sw_review.py) |
| 查看已验证和试点能力 | [能力清单](capabilities.yaml) |

原生零件保存为 `.SLDPRT` 并保留特征树。交付前检查重建状态、实体数量和关键几何。

### 批量建模与断点续建

打开 SolidWorks 2025 后，在仓库根目录运行支架示例：

```powershell
python examples/create_bracket_from_drawing.py --output output/bracket.SLDPRT
```

每个阶段验证通过后，脚本在 `output/bracket_checkpoints/` 保存一对同名的 `.SLDPRT` 和 `.json`。发生错误时，修正原因后执行脚本打印的 `Resume:` 命令即可从上一个检查点续建。请把两份检查点文件放在同一目录。需要更换成品路径时，可在恢复命令中加上 `--output`。

## 验证与许可

```powershell
python scripts/validate_skill.py
python -m unittest tests.test_native_parametric
```

连接 SolidWorks 后，可运行 `python -m tests.skill_session_live_smoke` 验证跨进程会话、建模和保存。项目使用 [MIT 许可证](LICENSE)。
