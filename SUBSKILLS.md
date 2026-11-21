# SolidWorks Automation 子技能矩阵

项目只有一个 Skill。以下专项操作指南、脚本和参考资料归入 solidworks-automation。

这种结构参考多技能仓库的管理方式：根 README 负责总入口、安装方式、能力地图和调用路由；每个子技能负责某一类稳定工作流。

## 技能索引

| 子技能 | 状态 | 用途 | 入口 |
|---|---|---|---|
| `solidworks-vibecad` | experimental | 自然语言需求 -> 参数化设计计划、制造规则检查、执行摘要、审查门禁 | `subskills/solidworks-vibecad/GUIDE.md` |
| `solidworks-fillet-chamfer-cnc` | stable | CNC 安装座、参数/碰撞预检、语义选边、有界尺寸降级、孔槽和圆角口袋 | `subskills/solidworks-fillet-chamfer-cnc/GUIDE.md` |
| `solidworks-threaded-holes` | stable | M3-M12 螺纹孔、攻丝底孔、孔口倒角、螺纹属性和 STEP 输出 | `subskills/solidworks-threaded-holes/GUIDE.md` |
| `solidworks-engineering-drawing` | pilot | GB/T 第一角零件图/装配图、尺寸链、孔表、BOM、PDF/BMP 证据和制造交付审视 | `subskills/solidworks-engineering-drawing/GUIDE.md` |
| `autocad-automation` | stable | AutoCAD DWG/DXF 二维绘图、线稿矢量化、图层/文字/标注处理、导出和图纸自检 | `subskills/autocad-automation/GUIDE.md` |

## 推荐路由

```text
自然语言需求
  -> solidworks-vibecad
  -> 结构化 design_plan.json
  -> 按零件类型路由到专项子技能
  -> 工程图需求连接 solidworks-engineering-drawing
  -> 父技能 scripts/sw_*.py 执行 SolidWorks COM
  -> sw_review.run_review() 审查
```

## 什么时候用哪个

### solidworks-vibecad

用户说：

- “把这个需求参数化”
- “做一个 text-to-CAD 工作流”
- “把行业知识库和提示词模板固化”
- “先别直接建模，先出设计计划”

使用：

```text
subskills/solidworks-vibecad/GUIDE.md
```

### solidworks-fillet-chamfer-cnc

用户说：

- “CNC 安装座”
- “连接块/支架”
- “很多圆角和倒角”
- “减重口袋/长圆槽/沉孔板”

使用：

```text
subskills/solidworks-fillet-chamfer-cnc/GUIDE.md
```

### solidworks-threaded-holes

用户说：

- “M6 螺纹孔”
- “攻牙孔”
- “攻丝底孔”
- “Hole Wizard / ThreadFeatureData / CosmeticThread”

使用：

```text
subskills/solidworks-threaded-holes/GUIDE.md
```

### autocad-automation

用户说：

- “用 AutoCAD 画这个”
- “生成/修改 DWG 或 DXF”
- “把这张图片线稿转成 CAD”
- “批量检查图层、文字、块、外部参照”
- “导出 AutoCAD 原生预览并审查”

使用：

```text
subskills/autocad-automation/GUIDE.md
```

### solidworks-engineering-drawing

用户说：

- “生成零件图/装配图/工程图”
- “按 GB/T、第一角投影出图”
- “补齐尺寸链、孔表、BOM、标题栏”
- “审查工程图是否能交付制造”

使用：

```text
subskills/solidworks-engineering-drawing/GUIDE.md
```

该子技能可以被根技能、VibeCAD、孔槽/CNC 子技能或工程编排器按需连接；其他子技能不需要反向依赖它。

注意：普通“照图画 CAD”的最终版只保留原图矢量化线条，不保留手工猜测的外围轮廓、五官椭圆、Logo 三角线、水波线、替代文字或图内审查说明。

## 子技能目录规范

新增子技能时保持：

```text
subskills/<skill-name>/
├── GUIDE.md             # 专项操作指南
├── README.md            # 人类阅读入口
├── scripts/             # 可复用脚本
├── references/          # 实测经验、避坑和 API 说明
├── examples/            # 示例输入/输出
└── agents/              # 可选，不同客户端配置
```

## 质量门禁

每个子技能必须说明：

- 适用场景和不适用场景。
- 推荐调用父技能的哪些 `scripts/sw_*.py`。
- SolidWorks API 的稳定策略和降级策略。
- 输出文件和审查要求。
- 新踩坑应沉淀到 `references/`。
