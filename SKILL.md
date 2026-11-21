---
name: solidworks-automation
description: 创建、修改和验证 SolidWorks 原生参数化零件，保留可编辑的草图、尺寸、约束和特征树。
---

# SolidWorks 原生建模

需要 Windows、Python 3.10+ 和本机 SolidWorks。使用前运行 `python scripts/sw_preflight.py`，打开 SolidWorks，再用 `scripts.sw_skill_session.run_action("document")` 确认目标文档。

## 建模规范

以下规范适用于创建、修改或重建 SolidWorks 三维零件。操作细节见[原生参数化工作流](references/parametric-workflow.md)。

1. 编写 Python 建模脚本，直接调用已验证的原生 Python/COM 能力库。需要分步文档绑定与状态检查时，可调用 `NativeParametric`。需要跨 Python 进程续接当前草图时，可调用 `run_action()` 并传入 `session_id`。
2. 开工前核对目标文档，避免误修改其他打开的模型。根据图纸或需求列出尺寸、约束、特征顺序及推断项。图纸标注的圆弧使用原生圆弧。
3. 使用原生草图、驱动尺寸、几何约束和参数化特征，保留可编辑的 FeatureManager 特征树。禁止用 `solidworks_create_basic_part` 代替逐步建模。除非用户明确要求，禁止用 STEP、STL 或无历史实体导入替代原生建模。
4. 检查每张关键草图的定义状态，优先做到完全定义。草图坐标只用于定位，必须回读尺寸以确认其为驱动尺寸。连接轮廓端点前先检查 SolidWorks 是否已将两点合并，仅在缺少所需约束时显式添加。
5. 切除前用 `sketch_plane` 回读法向，根据实体位置明确指定切除方向。创建每个关键特征后检查执行结果、实体状态及重建错误。
6. 编写 Python 建模脚本时，每完成一张草图或一个特征，验收通过后立即保存原生零件检查点，确认保存成功后才能开始下一步。正在编辑的草图以退出编辑并验证通过为保存时点。记录检查点路径、最后保存的步骤和下一步。建模或保存失败时停止后续步骤，保留当前工作零件和最后一个可用检查点。重试同一任务时，优先修复当前零件中的失败步骤，必要时从最后一个可用检查点续建。找不到可用进度时报告阻塞。仅在首次开始新零件，或用户明确要求从空白重建时，调用 `new_part` 或 `NewDocument`。
7. 用 `model_state`、`measure_geometry` 或 `scripts/sw_review.py` 核对几何与保存结果。保存原生 `.SLDPRT`，检查文件存在且非空，保留最终文档窗口，并报告文件路径、主要尺寸、特征树及验证结果。
8. 扩展能力时，先完善原生能力库和单元测试，并通过真实临时 Part 回归验证。

原生脚本入口见[能力目录](references/native-capability-catalog.md)。[能力清单](capabilities.yaml)记录验证状态。使用新的 COM 接口前阅读[API 查证流程](references/api-lookup.md)。
