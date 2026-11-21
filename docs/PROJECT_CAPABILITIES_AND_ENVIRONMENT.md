# 项目能力、环境与使用条件

最后核对：2026-11-14（Asia/Shanghai）

本文面向本项目的实际使用者，回答三个问题：当前能做什么、哪些能力需要人工复核、运行需要什么环境。详细实现与能力等级仍以根目录 [`capabilities.yaml`](../capabilities.yaml) 为唯一真源。

## 1. 项目定位

本项目是一个 Windows 本地 CAD 自动化套件，可同时作为：

- 支持 Skill 的 Agent 项目；
- Python CLI/脚本库；
- CAD Studio 桌面工作台与任务队列；
- SolidWorks C# Add-in、开放格式后端和外部求解器的统一入口。

原生 SolidWorks 路线通过 COM/PIA 操作真实桌面会话，保留可编辑的草图、驱动尺寸、约束和 FeatureManager 特征树。无头路线用于开放格式、预览、DFM 和受限求解，不能伪装成原生 `SLDPRT/SLDASM/SLDDRW` 历史模型。

## 2. 能力等级

当前 `capabilities.yaml` 共声明 28 项能力：

| 等级 | 数量 | 含义 |
|---|---:|---|
| `verified` | 8 | 已有真机或结构化回归证据，可按规定流程使用 |
| `pilot` | 19 | 可试用，但必须保留证据并由工程师最终复核 |
| `not_implemented` | 1 | 当前不得宣称可交付 |

版本基线：SolidWorks 2024、2026；AutoCAD 2024。其他版本是兼容目标，必须结合本机实测结果判断。

## 3. 当前可稳定使用的核心功能

### 3.1 原生参数化零件建模

原生参数化零件建模默认使用 Skill CLI，其他特征使用原生 Python API。完整明细见 [`native-capability-catalog.md`](../subskills/solidworks-parametric/references/native-capability-catalog.md)。当前支持：

- 新建、打开、保存和关闭原生 Part；
- 在前视、上视、右视基准面或受支持的实体平面创建原生草图；
- 普通/构造直线、中心/角点矩形、同心双矩形、圆、圆弧、正多边形、直槽、样条、椭圆、抛物线、方程式曲线和草图文本；
- 原生 Convert Entities、Offset Entities、显式拾取点 Trim/Extend、草图镜像，以及线性/圆周草图阵列；
- 既有自由草图点移动、构造几何状态切换和显式实体删除；
- 草图实体端点、圆心、半径、类型和构造状态回读；
- 驱动尺寸、水平/垂直关系、原生 Fully Define 和定义状态回读；
- 原生凸台拉伸、切除拉伸、拔模角和方向控制；
- 以同草图唯一构造中心线为轴的原生旋转凸台和旋转切除，并回读实际角度与方向；
- 以两个完全定义草图创建单截面/单路径原生扫描凸台和扫描切除，并回读截面、路径和扭转控制类型；
- 命名基准面的正向/反向距离偏置，以及 2–16 张有序截面草图的原生放样凸台和放样切除；
- 原生草图点，语义顶点、直边、圆边、圆柱/圆锥面，沿曲线/圆边圆心/面中心/投影/交点/草图点六类参考点，直边/两平面/两点/圆柱或圆锥面/点+平面参考轴，三点重合/面边角度/双面中面/圆柱相切平行约束基准面，以及带平移和 XYZ 旋转的数值坐标系；
- 原生 EquationMgr 全局变量、普通方程式和尺寸驱动，并以逐行状态、实际尺寸及实体包络验证；
- 原生多实体 Combine 加、减和公共布尔；
- 可序列化的原生面持久引用，并支持保存—关闭—重开后解析；
- 原生 FeatureManager 回滚到指定特征前/后及恢复到树末尾；
- 原生实体 Move/Copy，支持显式平移、旋转参数和副本数；
- 闭合草图原生平面曲面、面等距、曲面缝合、接触填充、法向直纹曲面与单/双侧加厚实体；
- 原生能力库直接支持中面凸台、贯穿全部切除和中面切除；
- 特征树、草图吸收关系、错误码、重建状态和实体数量检查；
- 保存 `SLDPRT`，导出多视图预览并进行包络、孔特征和 B-Rep 证据复核。

项目规则要求每个关键草图优先完全定义；不得用 STEP/STL 导入或无历史实体替代用户要求的原生参数化模型。

本项目已经在当前 SolidWorks 2025 SP0 会话中完成两条额外实机回归：

- 100 × 60 mm 完全定义中心矩形，20 mm 原生凸台；
- 45 × 45 mm 草图、70 mm/45°向外拔模凸台、39 × 39 / 27 × 25 mm 双矩形、55 mm 切除；与源件的草图几何、特征参数及 24 个 B-Rep 顶点完全相等。
- 10 × 10 mm 截面绕构造中心线做 270°反向旋转凸台，再做 210°旋转切除；角度、方向、轴线、特征树、1 个实体和 10 × 40 × 40 mm 包围尺寸均实机回读通过。
- Ø6 圆截面沿 40 mm 直线原生扫描，随后以 Ø2 截面同轴扫描切除；包围尺寸 6 × 6 × 40 mm，前后体积 1130.973/1005.310 mm³ 与理论值一致。
- 37 mm 偏置平面上的 Ø12→Ø7 原生圆台放样，随后以 Ø4→Ø2 放样切除；包围尺寸约 12 × 12 × 37 mm，前后体积 2682.966/2411.742 mm³ 与圆台公式一致；11 mm 反向偏置亦已回读验证。
- 30 × 20 mm 草图的 40 mm 中面凸台绝对边界为法向 `-20…+20 mm`；20 mm 中面切除和 Ø8 贯穿 40 mm 实体的体积分别与解析值一致。
- 草图偏移 5 mm、3×10 mm 线性圆阵列、4×360°/R20 mm 圆周阵列、实体边转换、两实体修剪/延伸，以及非对称直线关于中心线镜像的端点几何均已真机回读通过。
- 40×30×20 mm 块体已生成面中心参考点、对角两顶点轴、两平面交线轴、点+平面法线轴、直边重合轴、三点/37°/中面约束基准面；另建 Ø20×30 mm 圆柱和 Ø24→Ø12×30 mm 圆台验证两种旋转面中心轴；同时验证原点 `(7,-4,3) mm`、旋转 `(17°,23°,31°)` 的数值坐标系。点到平面残差、角度、中面偏距、全部轴参数及逆变换恢复原点均通过 API 回读。
- Delete Face 四种枚举模式均已验证：Default 将实体转开放曲面；Patch 删除 Ø10×5 mm 凸台并恢复 16,000 mm³ 基块；Fill 删除顶面后保持 24,000 mm³ 闭合块体；FillWithTangent 同样移除凸台并保持约 16,000 mm³ 单实体。
- 全局变量 `DepthGV=18 mm` 已驱动拉伸尺寸 `D1`，真实尺寸和实体包络从 10 mm 更新为 18 mm；EquationMgr 两行值状态均与行索引一致。
- 24,000 与 8,000 mm³ 两个相交实体的 Combine 加/减/公共结果分别为 26,000 / 18,000 / 6,000 mm³，均回读为单实体并重建成功。
- 1200 mm² 平面生成了 379 字节原生持久引用，保存、关闭并重开 SLDPRT 后以错误码 0 恢复，面积、中心和法向保持一致。
- `切除-拉伸1` 回滚前/回滚到特征前/恢复末尾的体积为 22,994.690 / 24,000 / 22,994.690 mm³，`IsRolledBack` 状态同步正确。
- 既有草图直线端点从 `(10,2)` 移至 `(12,5) mm`，构造状态切换成功，删除圆后实体数由 2 降为 1。
- 40×30×20 mm 实体平移到中心 `(7,-4,3) mm`；复制 1 份并沿 X 移动 50 mm 后回读两个实体中心为 0/50 mm。
- 40×30 mm 草图生成原生平面曲面，面积 1200 mm²；单侧加厚 5 mm 后实体体积为 6000 mm³。
- 1200 mm² 平面正/反向等距 5 mm 后分别位于 Z=15/5 mm；两个相邻 400 mm² 曲面缝合为一个 800 mm² 曲面体。
- Ø40 闭合草图生成分辨率 3 的原生填充曲面，面积 1256.637 mm²；40 mm 边生成 10 mm 法向直纹曲面，新增面积 400 mm²。
- 40×30×20 mm 块体删除顶面后生成 4000 mm² 开放曲面体；40×30 mm 平面用 Ø20 草图标准裁剪并保留外侧后面积为 885.841 mm²。
- 官方六边形平面解除剪裁后面积由 4663.527 增至 5165.841 mm²；40 mm 开轮廓拉伸 25 mm 生成 1000 mm² 原生拉伸曲面。
- 20 mm 母线绕 R10 轴旋转 270°生成 942.478 mm² 曲面；10 mm 截面沿 40 mm 路径扫描为 400 mm²；相隔 30 mm 的 20/30 mm 截面放样为 750 mm²。
- 两个独立凸台已原生重排，吸收草图同步移动且 1000/2000 mm³ 两实体体积不变；边/顶点持久引用在另一边 R2 圆角、保存关闭重开后均以错误码 0 恢复。

这证明当前机器上的原生参数化主链路可用，但不把 SolidWorks 2025 的所有项目能力自动升级为全量 `verified`。

### 3.2 孔槽、螺纹与常用精加工特征

- 盲孔、通孔、沉孔、沉头孔和半圆端槽；
- 孔位和直径验收；
- M3/M4/M5/M6/M8 公制攻丝底孔、真实 Thread/装饰螺纹降级路径；
- 常见圆角、倒角及 CNC 安装座子工作流。

复杂拓扑、保持线、多面高级圆角和生产级螺纹仍应按对应子技能门禁执行。

### 3.3 装配、配合与交付

- 添加零件/子装配体；
- 同心、重合、距离和齿轮配合；
- 固定/浮动组件及基础装配状态检查；
- STEP、STL、IGES、Parasolid、PDF、DXF 等导出；
- 批量导出、BOM CSV、Pack and Go 受控交付；
- 配置激活、命名尺寸更新和自定义属性。

装配与配合主能力为 `verified`，参数更新、BOM 和 Pack and Go 中的复杂引用场景仍为 `pilot`。

### 3.4 工程图与审查

- 原生工程图视图和模型尺寸插入；
- 第一角投影、剖视、尺寸链、孔槽表、BOM 和 PDF/BMP 证据；
- PDF 文字边界和预览碰撞检查；
- 等轴测、前视、俯视、右视预览；
- 包络、孔、实体数量、文件存在性和审查报告。

模型尺寸自动插入为 `verified`；完整制造工程图、自动尺寸链和 BOM 布局为 `pilot`，最终必须目视复核。

### 3.5 运动、Add-in 与高级路线

- Motion Study 创建、旋转马达、计算和结果新鲜度检查；
- C# `net48/x64` Add-in：应用事件、CommandGroup、TaskPane、PropertyManagerPage；
- 配置族、钣金、焊件、标准直齿轮；
- DFM、Routing 中性复核、复杂曲面/模具前置；
- CalculiX/Elmer FEA 输入、受限求解和网格收敛；
- OCCT/OCP 开放格式写入与受限 Loft/Sweep/Knit/Thicken。

除 C# Add-in 宿主外，上述大部分高级路线为 `pilot`；许可证、加载项、求解器和人工工程复核缺一不可。

当前实施主线只继续扩展通用原生参数化能力。根据 2026-11-19 的范围决定，模具分型、生产级钣金、生产级焊件以及现有齿轮 `pilot` 的稳定化验收暂缓；已有实现和证据继续保留，但这四项不计入“剩余原生能力”数量，除非用户以后明确重新纳入。

### 3.6 当前不可作为已完成能力的功能

- `autocad_basic_drafting` 当前为 `not_implemented`。
- AutoCAD 的 DXF 预览、SCR/AutoLISP 白名单桥和 .NET 后端是分开的 `pilot` 能力，不能据此宣称“AutoCAD 原生二维绘图已经全量稳定”。
- 复杂曲面通过离散采样不等于 Class-A 曲面；FEA 通过不等于安全认证；Motion 动画不等于真实机械自由度验证。

## 4. 最小运行环境

### 4.1 原生 SolidWorks 建模

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11，64 位 |
| SolidWorks | 合法安装、COM 注册正常、许可证可用；具体能力按版本基线判断 |
| Python | 3.10+，建议 3.12 |
| 核心依赖 | `pywin32>=305`、`comtypes>=1.2.0`、`pydantic>=2` |
| 运行方式 | 交互式 Windows 桌面会话；SolidWorks COM 写操作必须串行 |

安装核心依赖：

```powershell
python -m pip install -r requirements.txt
```

### 4.2 可选环境

| 能力 | 额外条件 |
|---|---|
| PDF/工程图最终审查 | PyMuPDF（已包含在 `requirements.txt`） |
| DXF 无头读写/预览 | `ezdxf>=1.3,<2` |
| STEP/IGES/BREP/GLB 无头几何 | `python -m pip install -r requirements-occt.txt` |
| OBJ/STL/GLB 网格处理 | `requirements-mesh.txt` 中的 trimesh、pygltflib、numpy、Pillow |
| 开放 FEA | CalculiX 或 Elmer；需配置求解器路径 |
| Motion Study | `swmotionstudy.tlb`、对应加载项和许可证 |
| Routing | SolidWorks Routing 类型库、加载项和许可证 |
| C# Add-in | .NET Framework 4.8、SolidWorks PIA、x64 RegAsm 管理员注册 |
| AutoCAD 原生后端 | 合法 AutoCAD 安装；具体版本与后端按能力清单门禁 |

缺少可选依赖只阻断对应能力，不应阻断普通原生零件建模。

## 5. 当前机器状态

2026-11-14 的诊断结果：

| 检查项 | 状态 |
|---|---|
| Windows | Windows 11，可用 |
| Python | 3.12.10，可用 |
| pywin32 / comtypes | 已安装 |
| PyMuPDF | 已安装 |
| SolidWorks | 2025 SP0，COM/安装注册可用 |
| Motion 类型库 | 已发现 `swmotionstudy.tlb` |
| AutoCAD | 2025 简体中文版，已检测到安装 |
| Codex / Claude / Gemini CLI | 已发现 |
| ezdxf | 未安装，仅影响 DXF 无头能力 |
| OCP/OCCT | 未安装，仅影响开放格式几何后端 |
| CalculiX | 未发现，仅影响开放 FEA 求解 |

本机 SolidWorks 2025 已通过当前项目的原生参数化建模实测，但正式版本声明仍遵循 `capabilities.yaml` 中的 2024/2026 基线。

## 6. 必须满足的操作条件

1. 原生 CAD 操作必须在同一登录用户的交互式桌面会话中运行。
2. SolidWorks 不能被模态对话框、许可弹窗或未完成命令阻塞。
3. 写操作必须串行；不要并行调用多个 SolidWorks COM 操作。
4. 每次操作前确认活动文档标题和路径，避免修改错误窗口。
5. API 内部长度单位为米；对用户报告和工具参数统一使用毫米。
6. 新增或修改 COM 工作流后，必须先运行单元测试，再用可自动关闭的临时文档做真实全链路测试。
7. 建模完成必须检查重建错误、实体数量、特征树、保存文件和多视图预览；关键复刻任务还应比较 B-Rep 或关键测量值。
8. 失败临时窗口应关闭；成功后保留最新已验证成果窗口。
9. `pilot` 能力必须人工复核；不得把预览非空、API 返回成功或求解器退出码 0 单独当作工程验收。
10. 缺少依赖时只安装任务需要的最小集合；修改 Python 环境、许可证或加载项前先取得用户确认。

## 7. 快速自检与启动

在项目根目录运行：

```powershell
python scripts\sw_preflight.py
python scripts\cad_studio.py doctor
```

使用 Skill CLI：

    python scripts/sw_skill_session.py --help

执行自动测试：

```powershell
python -m pytest
python tests\native_registry_smoke.py
```

若当前解释器没有安装 `pytest`，不要为了单个能力回归擅自修改运行环境；可先运行基于标准库 `unittest` 的目标测试，并按项目既有依赖管理方式补齐完整测试环境。圆角/倒角原生库回归可直接执行：

```powershell
python tests\test_sw_part_edge_features.py
python tests\native_edge_features_live_smoke.py
python tests\test_sw_part_shell.py
python tests\native_shell_live_smoke.py
python tests\test_sw_part_rib.py
python tests\native_rib_live_smoke.py
python tests\solidworks_configuration_family_regression.py --hidden
python tests\test_sw_part_hole_wizard.py
python tests\native_hole_wizard_live_smoke.py
python tests\test_sw_part_advanced_sketch.py
python tests\native_advanced_sketch_live_smoke.py
python -m unittest tests.test_sw_part_sketch_operations
python tests\native_sketch_operations_live_smoke.py
python -m unittest tests.test_sw_part_reference_geometry
python tests\native_reference_geometry_live_smoke.py
python -m unittest tests.test_sw_equations
python tests\native_equations_live_smoke.py
python -m unittest tests.test_sw_part_combine
python tests\native_combine_bodies_live_smoke.py
python -m unittest tests.test_sw_persistent_reference
python tests\native_persistent_reference_live_smoke.py
python -m unittest tests.test_sw_part_rollback
python tests\native_rollback_live_smoke.py
python -m unittest tests.test_sw_part_sketch_edit
python tests\native_sketch_edit_live_smoke.py
python -m unittest tests.test_sw_part_move_copy_body
python tests\native_move_copy_body_live_smoke.py
python -m unittest tests.test_sw_part_surface
python tests\native_surface_live_smoke.py
python -m unittest tests.test_sw_part_offset_surface tests.test_sw_part_knit_surface
python tests\native_offset_surface_live_smoke.py
python tests\native_knit_surface_live_smoke.py
python -m unittest tests.test_sw_part_fill_surface tests.test_sw_part_ruled_surface
python tests\native_fill_surface_live_smoke.py
python tests\native_ruled_surface_live_smoke.py
python -m unittest tests.test_sw_part_delete_face tests.test_sw_part_trim_surface
python tests\native_delete_face_live_smoke.py
python tests\native_trim_surface_live_smoke.py
python -m unittest tests.test_sw_part_untrim_surface tests.test_sw_part_extrude_surface
python tests\native_untrim_surface_live_smoke.py
python tests\native_extrude_surface_live_smoke.py
python -m unittest tests.test_sw_part_profile_surfaces
python tests\native_profile_surfaces_live_smoke.py
python -m unittest tests.test_sw_part_reorder
python tests\native_reorder_feature_live_smoke.py
python tests\native_persistent_edge_vertex_topology_live_smoke.py
```

常见诊断原则：

- `sw_preflight.py` 失败：先处理核心 COM 或 SolidWorks 注册问题；
- `doctor` 只有可选依赖 warning：普通 SolidWorks 建模仍可继续；
- Skill CLI 执行失败：检查活动文档、草图编辑状态、SolidWorks 模态窗口和特征错误码。

## 8. 项目结构

```text
solidworks-automation/
├── AGENTS.md                 # 本项目 Agent 建模规则
├── SKILL.md                  # 根 Skill 与工作流路由
├── capabilities.yaml         # 能力等级唯一真源
├── scripts/                  # SolidWorks/CAD Studio/审查/求解封装
├── subskills/                # 参数化、工程图、螺纹孔、CNC 等子技能
├── references/               # API、建模、装配、运动与排障说明
├── tests/                    # 单元、注册与真机回归测试
├── apps/                     # CAD Studio 桌面端和工作台
├── dotnet/                   # C# PIA/Add-in 后端
├── examples/                 # 示例工作流
└── docs/                     # 用户与项目说明
```

## 9. 推荐使用路线

- 普通零件创建/修改/复刻：`solidworks-parametric` → Skill CLI → 特征树与几何审查。
- 孔槽/螺纹/CNC：先进入对应子技能，再回到根审查流程。
- 工程图：`solidworks-engineering-drawing`，完成后检查 PDF/BMP 与尺寸语义。
- 装配和运动：先建零件和 Mate，再单独验证 Motion Study。
- 无 SolidWorks 的开放格式任务：CAD Studio/OCCT 路线；不要声称生成原生历史模型。
- 跨零件、装配、工程图、BOM 和多格式交付：使用工程编排 DAG，按阶段保存和验收。

## 10. 交付前检查清单

- [ ] 使用了与任务匹配且能力等级允许的后端；
- [ ] 活动文档与目标文件一致；
- [ ] 关键草图完全定义且尺寸为驱动尺寸；
- [ ] 特征错误码为 0，重建成功；
- [ ] 实体数量、包络和关键孔槽/曲面符合预期；
- [ ] 原生文件与要求的导出文件真实落盘且非空；
- [ ] 多视图预览已经人工查看；
- [ ] `pilot` 项已标注限制并完成人工工程复核；
- [ ] 临时/失败窗口已清理，最新成果仍保持打开。
