---
name: solidworks-automation
description: 创建、修改和验证 SolidWorks 原生参数化零件，保留可编辑的草图、尺寸、约束和特征树。
---

# SolidWorks 原生建模

需要 Windows、Python 3.10+ 和本机 SolidWorks。使用前运行 `python scripts/sw_preflight.py`，打开 SolidWorks，再运行 `python scripts/sw_skill_session.py document` 确认目标文档。

1. 根据图纸或需求列出尺寸、约束、特征顺序及推断项。标注圆弧使用原生圆弧。
2. 按[参数化工作流](references/parametric-workflow.md)使用分步 CLI。每个操作独立执行，用 `session_id` 续接。批量或复杂建模可直接调用 Python 封装。
3. 在写入前确认目标零件。保留驱动尺寸和原生特征树，核对草图定义状态，每个关键特征重建后检查错误和实体数。
4. 切除前用 `sketch_plane` 回读法向，根据实体位置明确指定切除方向。
5. 用 `model_state`、`measure_geometry` 或 `scripts/sw_review.py` 核对几何与保存结果。保存原生 `.SLDPRT`，检查文件存在且非空，保留最终文档窗口。

原生脚本入口见[能力目录](references/native-capability-catalog.md)。[能力清单](capabilities.yaml)记录验证状态。使用新的 COM 接口前阅读[API 查证流程](references/api-lookup.md)。
