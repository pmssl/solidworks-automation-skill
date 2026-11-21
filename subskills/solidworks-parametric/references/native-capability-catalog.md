# SolidWorks 原生参数化能力目录

本目录记录项目已有入口。能力等级以项目根目录 `capabilities.yaml` 为准。

## 状态说明

| 标记 | 含义 |
|---|---|
| Skill CLI | 当前逐步会话工具，具有文档绑定和状态回读 |
| Script API | 项目已有原生 COM 封装；使用前后必须做真实 SolidWorks 验证 |
| Gap | 当前没有足够稳定的项目入口，必须扩展或报告不支持 |

## 1. 逐步 Skill CLI

以下命令通过 scripts/sw_skill_session.py 执行：

| 工具 | 能力 | 关键验证 |
|---|---|---|
| `begin` | 绑定精确 Part，在标准基准面或受支持实体面开始草图 | 文档标题、草图名、`session_id`、编辑状态 |
| `offset_plane` | 从命名基准面创建距离偏置参考平面，可反向 | 回读特征类型、实际距离、方向和重建状态 |
| `rectangle` | 原点中心矩形 | 实际宽高；尺寸另行添加 |
| `rectangle_pair` | 外框和内框同心双矩形 | 四个驱动尺寸；定义后回读 X/Y 坐标 |
| `line` | 精确起终点直线，可创建构造中心线 | 回读真实端点和构造状态 |
| `corner_rectangle` | 两对角点矩形 | 回读四边和实际角点 |
| `circle` | 圆心和半径圆 | 回读圆心与半径 |
| `arc` | 圆心、起点、终点圆弧，可选顺/逆时针 | 校验等半径并回读圆心、端点与半径 |
| `polygon` | 圆心、外接半径和边数正多边形 | 回读边数；SolidWorks 会同时生成构造圆 |
| `straight_slot` | 轴线两端点和总宽度直槽 | 总宽度回读；端圆弧半径为宽度一半 |
| `spline` | 3-100 点原生样条 | 使用 SAFEARRAY(double)；回读真实 Spline 段 |
| `geometry` | 草图实体类型、端点、圆心和半径只读检查 | 直接读取实际草图，不使用请求缓存 |
| `dimension` | 矩形水平或垂直驱动尺寸 | `driving=true`、数值回读 |
| `relation` | 选择边的水平/垂直关系 | 草图不能过定义或无解 |
| `auto_define` | 原生 Fully Define，不使用 Fix | 定义后复查几何是否改变 |
| `status` | 读取真实约束状态 | `fully_defined` 和状态码 |
| `finish` | 退出草图 | 默认拒绝未完全定义草图 |
| `extrude` | 凸台/切除、深度、凸台拔模与方向 | 特征对象、错误码、重建、实体数、绝对边界 |
| `revolve` | 围绕草图中唯一构造线旋转凸台/切除 | 回读实际角度、方向、凸台/切除语义、轴线、重建和实体数 |
| `sweep` | 将既有完全定义截面沿当前会话的完全定义路径扫描凸台/切除 | 对象选择 mark 1/4；回读截面/路径类型、扭转控制、特征语义、重建和实体数 |
| `loft` | 按顺序连接 2–16 张完全定义截面草图，创建放样凸台/切除 | 回读截面数量、凸台/切除语义、闭合/相切状态、重建和实体数 |
| `model_state` | 特征树、吸收草图、错误码、实体数 | 预期特征存在且错误码为 0 |

### 已验证组合

- 中心矩形 → 驱动尺寸 → Fully Define → 凸台；
- 中心正方形 → 45°向外拔模凸台；
- 同心双矩形 → 四个驱动尺寸 → 环形切除；
- 直线、角点矩形、圆、圆弧、正多边形、直槽和三点样条；
- 图元创建后读取真实端点、圆心、半径、类型和构造状态；
- 标准基准面正向拉伸/切除；
- 最大外侧平面继续建模，并验证凸台向实体外生长。
- 单一构造中心线 → 270°反向旋转凸台 → 210°旋转切除；回读角度、方向、特征类型、轴线、实体数和包围尺寸。
- Ø6 圆截面沿 40 mm 直线路径扫描凸台，再以 Ø2 同轴截面扫描切除；回读特征树、6 × 6 × 40 mm 包围和前后理论体积。
- 11 mm 反向/37 mm 正向偏置基准面；Ø12→Ø7 圆台放样凸台，再以 Ø4→Ø2 放样切除；包围和前后体积与圆台公式一致。
- 原生能力库直接调用：40 mm 中面凸台、20 mm 中面切除和 40 mm 厚实体的贯穿全部切除；终止条件、绝对对称边界和体积均真机回读通过。

## 2. 原生文档及其他操作

通过 CLI 的 document、new_part、save_part、model_state 查看、新建、保存和检查零件。打开、关闭、导出和审查使用 sw_session.py、sw_export.py、sw_review.py。孔槽、配置、命名尺寸、属性与 Pack and Go 分别使用 sw_hole_features.py、sw_document_data.py 和 sw_delivery.py。

## 3. 原生 Script API：草图

文件：`scripts/sw_part.py`

| 函数 | 能力 |
|---|---|
| `start_sketch` / `sketch` / `end_sketch` | 标准基准面草图上下文 |
| `find_largest_outer_planar_face` | 查找最大外侧平面 |
| `start_sketch_on_largest_planar_face` | 在现有实体外表面继续草图 |
| `sketch_point` | 原生二维草图点；已通过 `swRefPointSketchPoint` 真机回读验证 |
| `sketch_line` | 直线 |
| `sketch_rectangle` | 中心矩形 |
| `sketch_corner_rectangle` | 角点矩形 |
| `sketch_circle` | 圆 |
| `sketch_arc` | 圆弧 |
| `sketch_polygon` | 多边形 |
| `sketch_slot` | 槽 |
| `sketch_spline` | 样条；不得替代有明确半径的圆弧 |
| `start_3d_sketch` / `end_3d_sketch` / `sketch_3d` / `sketch_point_3d` / `sketch_line_3d` / `sketch_spline_3d` | 原生 3D 草图生命周期、精确 XYZ 点/直线和 3D 样条 | `3D草图1` 已真机回读 segment types 0/3；直线 `(1,-2,3)→(11,12,23) mm`、样条端点 `(30,0,0)→(42,3,25) mm` 均与请求一致；独立点 `(0,0,18) mm` 已作为 Dome 约束点回读并驱动真实特征 |
| `sketch_ellipse` | 解析椭圆；中心、长短半轴和旋转角，已真机验证 |
| `sketch_parabola` | 有界解析抛物线；焦点、顶点和端点，已真机验证 |
| `sketch_equation_curve` | 原生参数方程式曲线；表达式与参数范围，已真机验证 |
| `sketch_text` | 原生草图文本；位置、文本和宽度因子，已真机验证 |
| `sketch_convert_entities` | 将显式模型边/草图实体转换到当前草图；已在实体面草图真机验证 |
| `sketch_offset_entities` | 单/双向偏移、链、端帽、构造和尺寸选项；5 mm 直线偏移已真机验证 |
| `sketch_trim` / `sketch_extend` | 通过显式实体和拾取点原生修剪/延伸；两实体修剪及延伸交点已真机验证 |
| `linear_sketch_pattern` | 原生线性草图步进阵列；3×10 mm 圆阵列已真机验证 |
| `circular_sketch_pattern` | 原生圆周草图步进阵列；4×360°、R20 mm 圆阵列已真机验证；中心由 SW 根据种子和正 `ArcRadius` 推导 |
| `sketch_mirror_entities` | 按选择标记 1/2 原生镜像草图实体；非对称直线关于构造中心线镜像已真机验证 |
| `move_sketch_point` / `set_sketch_construction` / `delete_sketch_entities` | 编辑既有自由点、切换构造状态、显式删除草图实体；端点 `(10,2)→(12,5) mm` 和删除圆已真机验证 |
| `add_dimension` | 通用草图尺寸 |
| `display_dimension_attached_entities` / `rebind_sketch_dimension` | 读取尺寸附着实体；删除旧驱动尺寸并在替换实体上原生重建、恢复驱动值、名称与公差 | SW2025 的 `IAnnotation.SetAttachedEntities` 对驱动草图尺寸返回 False，因此不是原位改绑；10 mm 驱动尺寸从第一条线迁移到原长 25 mm 的第二条线后，第二条线实测 10 mm；增强回归同时保留名称 `WidthDrive`、双向公差 `[-0.2,+0.3] mm` 和两个附着实体。旧 DisplayDimension 的 COM 身份按 API 约束无法保留，调用方必须替换陈旧引用 |
| `add_sketch_relation` | 原生草图关系 |
| `sketch_relations` / `sketch_relation_summary` / `add_sketch_relation_to_entities` / `add_sketch_relation_direct` / `add_sketch_relations_direct_batch` / `set_sketch_relation_suppressed` / `replace_sketch_relation_entity` / `replace_sketch_relation_entities_batch` / `delete_sketch_relation` | 原生关系生命周期管理 | 非水平线添加水平关系、抑制后移动、恢复、把关系从第一条线重绑定到第二条线并删除，类型、实体数、坐标和关系总数均已真机验证；直接 RelationManager 入口不依赖选择集，使用 `swConstraintType_e` 和显式 Dispatch 数组；创建批处理先完整校验，后续关系失败时用 `DeleteRelation` 逆序回滚；既有关系实体替换批处理在失败时反向替换回滚。真机将水平/等长两关系从旧线批量迁移到 31.623 mm 斜线后，新线变为水平并与另一线等长，关系类型/实体数为 4/1 与 14/2 |
| `auto_dimension_sketch` | 自动尺寸；使用后必须复查设计意图 |

这些函数不自动获得 Skill CLI 的会话保护。使用时必须自行确认活动文档、草图对象、返回值和完全定义状态。

## 4. 原生 Script API：实体特征

文件：`scripts/sw_part.py`

参考几何同时覆盖：`solid_vertices` / `find_solid_vertices` 语义顶点、`reference_points` 及沿曲线/圆边中心/面中心/投影/交点/草图点快捷入口、选择驱动的 `reference_axis` 及两点/两平面/圆柱或圆锥面/点+平面/直边语义快捷入口、`constraint_reference_plane` 及三点/角度/中面快捷入口、`coordinate_system_numeric`；上述模式均已在 SW2025 真机验证。

| 函数 | 能力 | 注意事项 |
|---|---|---|
| `extrude_boss` | 单向凸台、合并、拔模 | 验证方向、角度和实体数 |
| `extrude_cut` | 盲切/贯穿切除、真实方向参数 | 验证切除与实体相交 |
| `extrude_midplane` | 兼容中面凸台入口 | 新代码优先使用语义明确的 `extrude_boss_midplane` |
| `extrude_boss_midplane` | 中面凸台，总深度参数 | 回读 `MidPlane (6)`、总深度、绝对对称边界和体积 |
| `extrude_cut_through_all` | 单方向贯穿全部切除 | 回读 `ThroughAll (1)`；方向必须指向材料侧 |
| `extrude_cut_midplane` | 中面切除，总深度参数 | 回读 `MidPlane (6)`、总深度和切除体积 |
| `revolve_feature` / `revolve_boss` | 同草图构造中心线驱动的旋转凸台/切除及兼容凸台入口 | 逐步任务优先使用 Skill CLI；轴线和角度必须回读 |
| `revolve_feature_about_axis` | 独立原生基准轴驱动的旋转凸台/切除 | 官方选择契约为 profile mark 0、`AXIS` mark 16；R10→R20、高 10 mm 环形实体生成 `基准轴1`/`旋转1`，FeatureData 轴类型 5、体积 `9424.777961 mm³`、包络 `10×40×40 mm`，已真机验证 |
| `reference_axis_from_sketch_line` / `revolve_feature_about_sketch_segment` | 另一张草图中的直线经原生基准轴驱动旋转 | SW2025 将外部线识别为 `swSelEXTSKETCHSEGS=24`，不能直接传给 `FeatureRevolve2`；组合入口生成可编辑 `基准轴1` 后旋转，`草图1→基准轴1→草图2→旋转1`、轴类型 5、体积 `9424.777961 mm³`、实体包络 `10×40×40 mm` 已真机验证 |
| `revolve_feature_about_edge` | 现有实体直边直接驱动旋转凸台/切除 | profile mark 0、edge mark 4；60 mm 实体直边直接生成轴类型 1 的 `旋转1`，与 8×60×4 mm 基块保持两实体，体积 `1920.000000/9424.777961 mm³`、旋转体包络 `10×40×40 mm`，已真机验证 |
| `revolve_feature_two_directions` | 两个独立盲角度的双向旋转凸台/切除 | `SingleDir=False`，120°/60° 回读，FeatureData 类型 2、同草图轴类型 10、半环体积 `4712.388980 mm³`，已真机验证 |
| `revolve_feature_midplane` | 关于草图平面对称的中面旋转凸台/切除 | `swEndCondMidPlane=6`，输入为两侧合计总角度且 `ReverseDir` 固定无效；150° 总角度回读为两侧各 75°，FeatureData 类型 1、体积 `3926.990817 mm³`、包络 `[2.588,-5,-19.319]→[20,5,19.319] mm`，已真机验证 |
| `revolve_thin_feature` | 开轮廓薄壁旋转；支持单/双旋转方向和四种 `swThinWallType_e` 壁厚模式 | 中面总厚 2 mm 的 R15×10 mm 开线旋转 360°，生成 `旋转-薄壁1`；壁型 2、厚度回读 2 mm、R14–R16 解析体积 `1884.955592 mm³`、包络 `10×32×32 mm`，已真机验证；双厚度/双旋转方向已覆盖严格离线契约 |
| `revolve_feature_to_reference` | 到顶点、到面和距面偏置终止的单向旋转凸台/切除 | profile mark 0、目标引用 mark 32；到右视基准面生成 90° 环段、体积 `2356.194490 mm³`；到实体顶点反算 60°、旋转体积 `1570.796327 mm³`；距右视基准面 5 mm、`offset_reverse=False` 生成面前环段、体积 `1845.016800 mm³`，三种模式均以 B-Rep/解析体积和重建状态真机验证 |
| `revolve_feature_two_directions_to_same_reference` | 两个旋转方向以独立条件终止到同一顶点/面/偏置面 | 目标只选一次 mark 32，`SingleDir=False`、`BothDirectionUpToSameEntity=True`；双“到面”得到两侧各 90° 半环、体积 `4712.388980 mm³`；方向 1 到面、方向 2 距同一面 5 mm 且反向偏置得到 `5223.566670 mm³`，两种模式均为 FeatureData 类型 5 并已真机验证 |
| `revolve_feature_two_references` | 两个旋转方向分别终止于不同顶点/面/偏置面 | 方向 1 目标 mark 32、方向 2 目标 mark 64，`BothDirectionUpToSameEntity=False`；右视面 90° + 原生 60°角度基准面得到 150° 环段、体积 `3926.990817 mm³`、包络 `[0,-5,-20]→[20,5,17.321] mm`，已真机验证 |
| `revolve_feature_blind_and_reference` | 一个方向为盲角、另一方向到顶点/面/偏置面 | 引用位于方向 1 时 mark 32，位于方向 2 时 mark 64；方向 1 盲角 45°、方向 2 到右视面 90° 得到 135° 环段，FeatureData 类型 2、体积 `3534.291735 mm³`、包络 `[0,-5,-14.142]→[20,5,20] mm`，已真机验证 |
| 所有实体旋转入口的 `affected_bodies` | 多实体零件中的显式特征作用域 | 实体以 mark 1 追加，`UseFeatScope=True`、`UseAutoSelect=False`；双环体均与切除轮廓相交时，scope count 1 仅将下环从 `7539.822369` 切到 `4750.088092 mm³`，上环保持不变，已真机验证 |
| `sweep_feature` | 两草图扫描凸台/切除 | 截面 mark 1、路径 mark 4；逐步任务优先使用 Skill CLI |
| `sweep_boss_with_guides` | 原生凸台扫描的截面、路径与一个或多个导引草图 | 截面 mark 1、路径 mark 4、guide mark 2；Ø20 圆截面沿 40 mm 路径并受偏置导引线控制，回读 1 条 guide、12567.391 mm³ 体积和约 25.05 mm 横向包络，已真机验证 |
| `sweep_cut_with_guides` | 原生切除扫描的截面、路径与一个或多个导引草图 | 使用 SW2025 `InsertCutSwept5` 22 参数签名；Ø4 圆截面沿 40 mm 路径及偏置导引线从既有导引线凸台去除 `502.618632 mm³`，解析误差 `7.2×10⁻⁵`，回读 1 条 guide，已真机验证 |
| `sweep_feature_advanced` | 非薄壁凸台/切除扫描的路径方向、双向路径及常量扭转控制 | SW2025 `InsertProtrusionSwept4`/`InsertCutSwept5` 完整签名；Ø6 圆截面以路径中点为起点双向扫描得到 40 mm 长、`1130.973355 mm³` 单实体；8×4 mm 矩形沿 40 mm 直线路径扭转 90°，枚举 8（沿路径常量扭转）和 9（法向恒定+常量扭转）均回读 90°、体积 `1279.995906 mm³`、单实体且重建通过。非圆截面的路径起点应与截面草图实体点建立明确重合；仅落在截面内部但无对应草图点的基线在 SW2025 返回空特征 |
| `sweep_thin_feature` | 闭合轮廓薄壁凸台/切除扫描，可选导引线、四种壁厚模式、方向和扭转参数 | SW2025 已验证闭合 Ø10 圆沿 40 mm 路径：单向外侧 2 mm 得到 R5–R7、`3015.928947 mm³`；中面总厚 2 mm 得到 R4–R6、`2513.274123 mm³`；FeatureData 回读薄壁状态、类型与厚度。官方 Sweep Rules 明确实体 Boss/Base Sweep 的草图轮廓必须闭合；`ThinFeature` 只控制闭合轮廓壁厚，不使开轮廓合法。能力库现对开轮廓提前阻断并提示使用 `sweep_surface` + `thicken_surface` 的两特征原生替代路线 |
| `offset_plane` | 命名平面的距离偏置参考平面 | 支持距离和反向；逐步任务优先使用 Skill CLI |
| `constraint_reference_plane`、`reference_plane_geometry` 及三点/角度/中面/相切平行/平行过点/曲线端点法向/曲线位置法向/曲面投影点相切快捷入口 | 1–3 个显式实体引用的约束基准面；Transform 世界几何回读 | 选择标记 0/1/2；支持 SW2025 类型库约束值；三实体顶点重合、实体面+铰链边 37°、两相对实体面中面、Ø20 圆柱相切平行、平行实体面并通过指定顶点、40 mm 直边端点法向平面均已真机验证；曲线位置法向入口先创建保留在 FeatureManager 的原生沿曲线参考点，再让基准面依赖该点，25% 位置回读点 `[10,15,10] mm`、法向 `[-1,0,0]`、点面残差 0；曲面投影点相切支持最近位置和沿草图法向两模式，分别在圆柱上回读 X=10 mm/法向 X 与 Z=10 mm/法向 Z 的真实相切面；平行过点用 B-Rep 法向/中心定位参考面，不依赖界面语言；原点/法向必须从 Transform 读取 |
| `loft_feature` | 2–16 张有序截面草图放样凸台/切除 | 截面 mark 1；逐步任务优先使用 Skill CLI |
| `loft_boss_with_guides` | 多截面、一个或多个分组导引曲线及可选中心线的原生凸台放样 | 截面 mark 1，导引组 mark `4096*n+2`，中心线 mark 4；Ø40→Ø20、30 mm 高圆截面加单条 3D 直线导引已真机回读 1 条 guide、单实体和 21993.006 mm³ 体积 |
| `loft_cut_with_guides` | 多截面、一个或多个导引曲线及可选中心线的原生切除放样 | SW2025 `InsertCutBlend`：截面 mark 1、所有导引线 mark 2、中心线 mark 4；60×60×80 mm 基体内以 Ø20→Ø10、长 30 mm 截面和单条 3D 直线导引创建 `切除-放样1`，回读 1 条 guide、`IsBossFeature=false`、去除 `5498.118805 mm³`，与圆台解析值差 `0.331662 mm³`，单实体重建通过 |
| `loft_feature_advanced` | 中心线、闭合、薄壁以及法向/方向向量/依附面相切端部约束的原生凸台/切除放样 | 中心线凸台/切除分别回读非空 Centerline 并以解析圆台体积验证；Ø20→Ø10、30 mm 中面总厚 2 mm 的薄壁凸台/切除均得到 `2866.434312 mm³`；四个正交圆截面配闭合 3D 导引线生成 `Close=true` 的 2934.211361 mm³ 闭合实体；法向约束与 X 向基准轴方向约束分别得到 7549.017822/6158.119878 mm³；圆柱顶面作为首截面、匹配类型 3 与末端法向约束生成 8735.612519 mm³ 合并实体，保留一个圆柱面并回读 start/end 类型 3/1。SW2025 公开 `InsertProtrusionBlend2`/`InsertCutBlend` 仅接受匹配类型 0..3；UI 的“曲率到面”未由该公开签名暴露 |
| `boundary_feature` / `boundary_boss` / `boundary_surface` | 原生 Boundary 实体与曲面封装（实验） | SW2025 类型库与官方帮助确认 `InsertNetBlend2` 为当前入口，`InsertNetBlend` 已废弃；实体 D1/D2 标记为 8193/8194 并按曲线索引增加 8192，Boundary Surface 的 D1/D2 标记为 1/2。真实 B-Rep 边选择已回读为 `swSelEDGES(1)`、mark 1/2；直接 `InsertNetBlend*` 对已测网格仍返回空，必须同时使用 `allow_experimental=True` 和 `SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC=1`，不得标记为已支持。`boundary_surface_command` 曾经通过 `RunCommand(618)` 生成 `NetBlend` 和 300 mm² 曲面，但该 PropertyManager 路径触发用户可见保存窗口，现仅保留为人工诊断并从 `native_*_live_smoke.py`/无人值守能力中排除 |
| `solid_edges` / `edge_geometry` / `find_solid_edges` | 实体边枚举、直边几何摘要与语义解析 | 使用长度、无向方向和中点，不依赖 `Edge1` 或屏幕坐标；已真机验证 |
| `circular_edge_geometry` / `find_circular_edges` | 圆边中心、轴和半径语义解析 | Ø20 圆柱顶圆边已真机验证；供圆边中心参考点等能力复用 |
| `reference_points` 及语义快捷入口 | `swRefPointType_e` 2–7 全部原生参考点类型 | 沿曲线距离/0–100 百分比/均布、圆边圆心、面中心、面上顶点投影、两边交点和草图点均已真机验证 |
| `fillet` | 等半径边圆角 | 显式边对象选择、正半径校验、特征定义/体积/拓扑回读；R3 单直边已真机验证 |
| `chamfer` | 角度-距离边倒角 | 显式边对象选择、距离和角度校验；2 mm/37° 单直边已真机验证 |
| `linear_pattern_feature` | 单方向线性特征阵列 | 显式方向边与种子特征、数量和间距回读；3×15 mm 孔阵列已真机验证 |
| `circular_pattern_feature` | 单方向圆周特征阵列 | 显式圆边轴与种子特征、总角度和数量回读；5×360° 孔阵列已真机验证 |
| `solid_faces` / `planar_face_geometry` / `find_planar_faces` | 实体面枚举与平面面语义解析 | 支持面积、中心和无向法向筛选；已真机验证 |
| `cylindrical_face_geometry` / `find_cylindrical_faces` / `conical_face_geometry` / `find_conical_faces` | 圆柱/圆锥面参数回读与语义解析 | 圆柱原点/轴/半径；圆锥 `ConeParams2` 原点/轴/半径/半角/参考方向；Ø20×30 mm 圆柱和 Ø24→Ø12×30 mm 圆台已真机验证 |
| `reference_axis` 及语义快捷入口 | 单实体直边、单草图直线、两平面交线、两点、圆柱/圆锥面中心线、点+平面法线参考轴 | SW2025 `swRefAxisType_e` 五种类型及圆柱/圆锥旋转面分支均通过 `InsertAxis2` 真机验证；外部草图直线到可编辑基准轴也已由旋转链路验证 |
| `shell` | 抽壳 | 显式移除面、壁厚和内外方向；40×30×20 块体单面移除、2 mm 内向抽壳已真机验证 |
| `mirror_feature_objects` / `mirror_feature` | 特征镜像 | SW2025 官方选择标记：种子特征 mark 1、镜像基准面 mark 2；80×60×10 mm 基块上的 Ø6 贯穿切除关于右视基准面镜像后，种子数 1、体积 `47434.513322 mm³`，已真机验证 |
| `combine_bodies` | 多实体加/减/公共 | 原生 `CombineBodies`；24,000 与 8,000 mm³ 相交块体分别验证 26,000 / 18,000 / 6,000 mm³ 和单实体结果 |
| `intersect_bodies` | 原生 Intersect 区域预览、按索引/唯一体积选择区域、合并与消耗控制 | SW2025 必须使用强类型 `FeatureManager`、`PreIntersect2`、预览后清选以及 `SAFEARRAY(VT_BOOL)` 排除数组；两个相交实体回读 2,000/6,000/18,000 mm³ 三个区域，仅保留交叠区得到 6,000 mm³，全区域合并得到 26,000 mm³；`Sculpt` 特征、2 个工具、3 个区域、错误码 0 和重建成功均已真机验证 |
| `rollback_to_feature` / `rollback_to_end` | 原生回滚条控制 | 切除特征前后体积 22,994.690 → 24,000 → 22,994.690 mm³，`IsRolledBack` 状态同步验证 |
| `feature_dependency_graph` / `feature_dependency_path` / `reorder_feature_after_safe` | 原生 Feature 父子依赖递归图、路径解析和依赖安全重排 | 从孔口 `圆角1` 递归读取 `GetParents/GetChildren`，得到 7 个稳定名称/类型节点和 11 条边；明确包含 `凸台-拉伸1 → 切除-拉伸1 → 圆角1`，同时覆盖草图、前视基准面与原点依赖；三个建模特征错误码 0、重建成功。图节点按名称+`GetTypeName2` 去重，不依赖 Python COM 代理身份。父特征移到其后代之后的非法请求会在 `ReorderFeature` 前阻断；真机验证 `凸台-拉伸1 → 圆角1` 路径、特征顺序不变且错误码全 0 |
| `reorder_feature_after` | 独立特征及整个 FeatureManager 文件夹重排 | 两个独立凸台顺序反转，吸收草图随父特征移动；另将包含 1000 mm³ 实体凸台的 `First Body` 整体移动到包含 2000 mm³ 实体凸台的 `Second Body` 之后，顶层顺序从 First/Second 变为 Second/First，两个实体体积和重建状态均保持不变 |
| `create_feature_folder` | 创建命名及嵌套 FeatureManager 包含文件夹 | 基础用例把 80×60×10 mm 板的凸台与 Ø6 贯穿切除放入 `Machining Features`；嵌套用例进一步把 `Machining Inner`（凸台和第一切除）与第二切除放入 `Machining Outer`，内外层子项均从 FolderFeature 回读，错误码 0、重建成功，实体体积 `47214.601837 mm³` 与双 Ø6 切除解析值一致 |
| `move_copy_bodies` | 原生实体移动/复制 | 非对称平移 `(7,-4,3) mm` 与 X=50 mm 单副本已回读实体中心和数量 |
| `scale_feature` / `scale_feature_evidence` | 原生缩放特征 | 支持按质心、原点或自定义坐标系的均匀与非均匀 XYZ 缩放及可选实体作用域；SW2025 已用 1.5×0.5×2.0 与后续 0.5 倍缩放回读 `IScaleFeatureData`、60×15×40 / 30×7.5×20 mm 包络、36000 / 4500 mm³ 体积；另以 X=10 mm 原生坐标系对指定实体放大 2 倍，FeatureData 保留坐标系和 1 个实体作用域，包络由 40×30×20 变为 80×60×40 mm、中心移至 X=-10 mm、体积 192000 mm³，错误码 0且重建成功 |
| `dome_feature` / `update_dome_feature` / `dome_feature_evidence` | 单面/多面原生圆顶特征及定义编辑 | 选定面必须按官方契约使用 mark 1；SW2025 在 40×30×20 mm 块体相对两面分别创建 8 mm 普通圆顶和 5 mm 椭圆圆顶，体积从 24000→28266.542→30933.003 mm³。另已验证垂直实体边作显式方向、`(0,0,18) mm` 原生 3D 草图点作约束、4 mm 反向凹圆顶；方向回读非空，加入约束点后 SolidWorks 按官方语义将 Height 归零并清除显式方向，反向圆顶将体积从 27993.837 降至 25860.420 mm³。`IDomeFeatureData2`、错误码 0和重建均通过；`GetBodyBox` 对曲面仅为近似值，精确参数以 FeatureData 为准 |
| `indent_feature` / `indent_feature_evidence` | 多实体原生压凹/压印与切除 | 官方选择契约为目标 Body mark 1、工具区域 mark 4；Body2 使用其专有 `Select2(Append, ISelectData)`。SW2025 以 Ø16×15 mm 工具体作用于 60×40×10 mm 目标体：2 mm 厚、1 mm 间隙的非 Cut 压印将目标体积 24000→22969.558 mm³；0.5 mm 间隙 Cut 模式将目标体积降至 21730.199 mm³。曲面工具必须传面区域而非整个 SurfaceBody；X=5 mm 平面切除的 `cut_direction=False/True` 分别保留 10000/14000 mm³ 和相反半空间，体积之和为原目标 24000 mm³。各模式均保留工具体/曲面体，`IIndentFeatureData` 回读单目标/单区域、错误码 0且重建成功。旧式 `InsertIndent` 即使在 UI 不使用厚度的 Cut 模式也要求正厚度占位，0 会返回空特征 |
| `flex_feature` / `flex_feature_evidence` | 原生 Flex 弯曲、扭转、锥化和拉伸 | `InsertFlexFeature` 的 Body2 必须使用官方页面未注明的 mark 1；左右修剪值是两侧各自的非负距离，不是有符号坐标。SW2025 已验证四种枚举：10×10×100 mm 长杆 30° 弯曲、40/40 mm 修剪后体积 10000→9998.402 mm³；12×6×100 mm 长杆以原生 Amount=0.2 扭转后包络 12×6.09×101.5 mm、体积比 1.000075，锥化后包络 12.539×7.168×100 mm、体积比 1.000324，拉伸后包络 12×6×105.093 mm、体积比 1.050930。弯曲/扭转/锥化的 D0 按弧度回读；Stretch 会把旧式 Angle 入参归一化为实际轴向距离，本用例 D0=5.092958 mm并与 Z 增量一致。四种模式均为单实体、错误码 0并重建成功；本机 `GetTypeName2` 对整个 Flex 家族统一返回 `Bending`，必须结合请求枚举、D0、轴角色和几何变化验收 |
| `planar_surface_from_sketch` / `thicken_surface` | 基础原生曲面与加厚 | 40×30 mm 平面曲面面积 1200 mm²，单侧 5 mm 加厚体积 6000 mm³ |
| `offset_surface` | 面等距曲面 | 1200 mm² 平面从 Z=10 mm 正/反向偏置 5 mm 后分别位于 Z=15/5 mm |
| `knit_surfaces` | 曲面缝合 | 两个相邻 400 mm² 平面按选择 mark 1 缝合为一个 800 mm² 曲面体，容差参数已回读 |
| `fill_surface` | 闭合边界填充曲面、内部约束曲线及相切边界 | Ø40 草图生成 1256.637 mm² 单曲面体；增加端点落在圆周、中心抬高 8 mm 的 3D 样条后，FeatureData 回读 1 条内部约束曲线，曲面面积增至 1421.210 mm²、Z 包围约 -5.714..10.014 mm；Ø40×25 mm 圆柱曲面边界以 mark 513 创建相切填充，FeatureData 从自身 `GetPatchBoundary` 实体回读 `swTangent=1`、填充面积 3756.437 mm²；分辨率 3、错误码 0 和重建均已真机验证。`swCurvature=2` 已分别用圆柱单边界、带孔平面单边界和删除 40×30×20 mm 长方体顶面所得四边开口验证，SW2025 均返回特征但 FeatureData 回读 -1；四边用例只增加 1200 mm² 平面封口，因此仍属未实现 |
| `ruled_surface_from_edges` / `ruled_surface_evidence` | 边界直纹曲面全部五种模式 | `InsertRuledSurfaceFromEdge2` 创建值 0–4 与 FeatureData 枚举 1–5 相差 1。SW2025 已以 40 mm 平面边、10 mm 距离验证切向、法向、锥化向量、垂直向量和 Sweep：每种新增 400 mm² 曲面、错误码 0且重建成功；20°锥化包络投影为 9.397/3.420 mm，类型 2/3 通过强类型 FeatureData 各保留 1 个 30 mm 直边方向引用，Sweep 回读 `UseVector=true` 和 Z 数值向量。旧式创建方法的 XYZ 只可靠用于 Sweep；锥化/垂直模式由法向种子经 `SetDirectionReference` 原位完成 |
| `delete_faces` | 原生 Delete Face 全模式 | Default：块体转开放曲面；Patch：Ø10×5 mm 凸台恢复 16,000 mm³ 基块；Fill：删除块体顶面仍保持 24,000 mm³ 闭合实体；FillWithTangent：凸台恢复 `15999.999848 mm³` 单实体；四种 `swFaceDeleteOption_e` 均已真机验证 |
| `replace_faces` | 原生 Replace Face | 目标面 mark 1、替换曲面体 mark 2；40×30×20 mm 块体顶面由 Z=10 mm 平面替换为 Z=15 mm 平面，得到 30,000 mm³ 单实体和 `[-20,-15,-10,20,15,15] mm` 包围盒，已真机验证 |
| `trim_surface_standard` | 草图/曲面工具标准裁剪 | 40×30 mm 平面用 Ø20 草图裁剪并保留外侧，剩余面积 885.841 mm²；通过 `GetPreTrimmedBodies` 语义解析临时分片 |
| `trim_surface_standard(..., mutual_trim=True)` | 曲面互相裁剪，`pilot` | 已按类型库加入 mutual/keep-remove/split/sew/solid-result 参数和严格离线契约；两张正交原生拉伸曲面真机可正确预选 2 张曲面并在预处理后选中 1–3 个类型 75 的 `SURFACEBODY` 区域，但 SW2025 `PostTrimSurface` 仍返回空，暂不得宣称支持 |
| `untrim_surface` | 解除剪裁/自然边界延伸 | 官方六边形平面由 4663.527 增至 5165.841 mm²，生成 3 个曲面体；覆盖全部边、外部/内部边枚举入口 |
| `extend_surface` / `extend_surface_distance` / `extend_surface_evidence` | 曲面边/面的同曲面或线性延伸，支持按距离、到点、到实体面 | SW2025 以 40×30 mm 平面曲面的 40 mm 边验证：10 mm 同曲面与线性按距离延伸、到 Y=25 mm 的原生 3D 草图点、到 Y=25 mm 的实体平面面均得到 1600 mm² 单曲面体；FeatureData 回读 `Type=1/0`（同曲面/线性）、`EndCondition=0/1/2`、10/0 mm、单选择项、错误码 0且重建成功。API 的到面条件仅接受实体面，公共入口强制引用/距离参数互斥 |
| `flatten_surface` / `flatten_surface_evidence` | 原生曲面展平，含待展平面、锚点、精度和基础撕裂开关 | 官方选择角色为面/曲面 mark 1、锚点顶点 mark 16；SW2025 将 R10×20 mm、270°圆柱片以精度 3 展平，源面积 942.477796 mm²、展开面积 942.466823 mm²（误差约 0.00116%），结果保留源曲面和展开曲面两个实体。FeatureData 回读 1 个面、有效锚点、无 guide/tear/map edge、错误码 0且重建成功；高级 relief/map 路径仍需独立回归 |
| `extrude_surface` | 开/闭草图原生拉伸曲面 | 40 mm 开轮廓拉伸 25 mm，生成一个 1000 mm² 曲面体；使用 SW2025 `FeatureExtruRefSurface3` 完整签名 |
| `revolve_surface` | 构造轴原生旋转曲面 | 20 mm 母线绕 R10 轴旋转 270°，生成一个 942.478 mm² 圆柱曲面体 |
| `sweep_surface` / `sweep_surface_evidence` | 开截面/路径、导引线与常量扭转的原生扫描曲面 | 截面/path/guide 使用官方 mark 1/4/2；10 mm 开截面沿 40 mm 直线路径基线为 400 mm²。SW2025 又以 20 mm 开截面验证导引线跟随模式：FeatureData 回读 1 条 guide、`TwistControlType=2`，面积由无导引线基线 800 降至 660 mm²；90° 常量扭转回读 `TwistControlType=8`、角度 π/2，面积 820.027 mm²且 Z 跨度 20 mm。两案均为单 `SweepRefSurface`、错误码 0、重建成功；导引线与双向或常量扭转组合按官方限制提前阻断 |
| `loft_surface` / `loft_surface_evidence` | 有序开/闭截面、导引线、中心线及方向约束的原生放样曲面 | 相隔 30 mm 的 20/30 mm 开截面无约束基线为 750 mm²；弯曲 3D 样条导引线与中心线分别生成 823.668/823.523 mm² 单曲面体，Y 向原生基准轴作起止方向约束生成 842.538 mm²。三者均为 `BlendRefSurface`、错误码 0、重建成功，父依赖分别保留 3D 草图或 `RefAxis`。SW2025 对 `BlendRefSurface.GetDefinition` 返回空，证据函数明确报告 `feature_data_available=false`，不伪造 `ILoftFeatureData` 回读 |
| `hole_wizard_simple` / `hole_wizard` | 原生 Hole Wizard 简单盲孔/贯穿孔 | 带模型空间选择点；优先 HoleWizard5，Toolbox 映射不可用时回退原生 IModelDoc2 HoleWizard；Ø6 贯穿孔已真机验证 |
| `rib_feature` / `rib` | 开轮廓筋 | SW2025 十参数签名、厚度/双侧/材料方向/拔模选项；L 形支架 3 mm 双侧筋已真机验证 |

这些函数表示项目已有封装，不表示每种参数组合都已独立 `verified`。复杂拓扑或重复需求应先增加白名单库模式和真实回归。

## 5. 孔槽与阵列 Script API

文件：`scripts/sw_hole_features.py`

- `create_blind_hole`
- `create_through_hole`
- `create_counterbore_hole`
- `create_countersink_hole`
- `create_semicircular_slot`
- `create_hole_pattern`

创建参数证据必须与 `solidworks_inspect_hole_features`、`collect_geometry_measurements()` 和孔位验收交叉验证。螺纹孔任务还要读取 `solidworks-threaded-holes`。

## 6. 参数、配置和属性 Script API

文件：`scripts/sw_document_data.py`

- `inspect_configurations`
- `activate_configuration`
- `create_configuration`
- `update_dimension_mm`
- `read_custom_property`
- `set_custom_properties`
- `feature_suppression_states` / `set_feature_suppression`：按当前、全部或指定配置设置原生特征抑制，并逐配置激活后以 `IFeature.IsSuppressed` 回读真实状态；
- `read_configuration_parameters`：通过 `IConfiguration.GetParameters` 只读配置参数矩阵，严格校验计数、名称/值长度与重复名，并分类尺寸、特征抑制和元数据；无设计表时明确标记官方准确性限制；
- `rename_configuration` / `delete_configuration`：原生配置重命名与安全删除；重命名验证完整父子图，删除默认拒绝隐式级联，显式子树模式会先切换活动配置并按叶到根顺序执行；
- `inspect_configuration_properties` / `update_configuration_properties`：配置备注、说明、备用名称、两种 BOM 显示开关和“抑制新特征”原生属性；活动目标设置非活动专属属性时自动临时切换并恢复；`BOMPartNoSource` 在 SW2025 动态与强类型 property-put 均静默不生效，因此只读；
- `audit_configuration_rebuilds`：逐配置激活并用 `ForceRebuild3(False)` 强制重建，回读 `IConfiguration.NeedsRebuild`、顶层 FeatureManager 错误码、实体数量、逐实体体积及合并包络，最后恢复原活动配置；不保存文件；

基础配置清单、配置创建/激活、命名尺寸按指定配置更新、配置级自定义属性写入与读取均已通过三配置原生零件的保存—关闭—重开真机回归。配置级特征抑制另以 80×50×12 mm 零件和 Ø10 通孔真机验证：仅“无孔”配置抑制 `切除-拉伸1`，三配置抑制状态为 false/true/false，实体体积为 47057.522/48000/47057.522 mm³。配置原生属性现覆盖备注、说明、备用名称、两种 BOM 显示开关和抑制新特征；属性回归中默认配置新增 Ø10 贯穿切除后体积为 `47057.522204 mm³`，属性配置因 `SuppressNewFeatures=True` 自动抑制该切除并保持 `48000 mm³`，证明属性行为真实生效；`BOMPartNoSource` 在 SW2025 动态和强类型入口均无法可靠写入，明确保持只读。`apply_configuration_family` 可在不打开 Excel、不保存文件的情况下批量创建/复用配置，并按显式配置作用域更新命名尺寸、属性和特征抑制；三配置深度 12/6/20 mm 真机回读体积 48000/24000/80000 mm³、配置属性一致。`audit_configuration_rebuilds` 又在同一 80×50 mm 三配置族上逐配置强制重建并验证 12/6/20 mm 包络深度、48000/24000/80000 mm³ 体积、单实体、零特征错误、`NeedsRebuild=False` 和活动配置恢复；全程不保存。显示状态现支持清单、创建、激活、重命名和非活动状态删除；真机生命周期后精确恢复默认状态列表。`create_derived_configuration` 与 `configuration_hierarchy` 已真机验证两级 `默认 → 派生一级 → 派生二级` 层级、父子双向回读和活动配置恢复。配置重命名/删除又以 `默认 → 父配置 → 子配置 → 孙配置` 真机回归：父配置重命名为“生产族”后子级 Parent 引用同步更新；活动孙配置所在子树按 `孙配置 → 子配置 → 生产族` 删除前自动切回“默认”，最终保留一个配置，实体包络完全不变且特征错误码 0。`read_configuration_parameters` 已在无设计表的 50×30 mm 零件上回读“参数组”的 `D1@凸台-拉伸1=6.000000`，并由真实尺寸和 6 mm B-Rep 深度交叉验证；`IConfiguration.SetParameters` 与 `IConfigurationManager.SetConfigurationParams` 在同一环境均未可靠回写，因此矩阵保持只读，写入继续走已验证的尺寸/抑制 API。`inspect_design_table` 可在不打开 Excel/OLE 的情况下读取既有设计表元数据，并正确识别 `GetDesignTable` 的 `-2` 占位代理；设计表创建/编辑仍为 `pilot`。所有操作仍须明确文件级/配置级作用域。

文件：`scripts/sw_equations.py`

- `add_equation` / `add_global_variable` / `add_dimension_equation`：原生 EquationMgr 方程式、全局变量和尺寸驱动；
- `equation_rows` / `evaluate_equations` / `global_variable_value`：逐行值、类型、配置作用域、禁用计数和重建检查；
- 已真机验证 `DepthGV=18mm` 驱动拉伸 `D1`，实体包络从 10 mm 深度变为 18 mm；逐行 `Value` 后 `Status` 分别为 0/1。

## 7. 专项原生能力

| 能力 | 路由 |
|---|---|
| 标准外啮合渐开线直齿轮 | `scripts/sw_gear.py` + `references/gears.md`，已有 `pilot` 实现；稳定化验收暂缓，不计入当前实施主线 |
| 真实螺纹孔 | `solidworks-threaded-holes` |
| 高级圆角/倒角 CNC 件 | `solidworks-fillet-chamfer-cnc` |
| 钣金、焊件 | 根 Skill 高级能力门禁，现有 `pilot` 保留；生产级专项能力暂缓，不计入当前实施主线 |
| 工程图 | `solidworks-engineering-drawing` |
| 装配体与运动 | 根 Skill 的装配/Motion 工作流 |

专项 Skill 可以细化设计规则，但仍必须遵守本 Skill 的活动文档、原生历史、重建、实体和保存验证底线。

### 当前暂缓的专项能力

根据 2026-11-20 的项目范围确认，以下能力保留现有代码、文档和试验结果，但暂不继续开发或稳定化验收，也不计入“剩余原生能力”数量：

- 模具分型专项能力组；
- 生产级钣金专项能力组；
- 生产级焊件专项能力组；
- 已有齿轮 `pilot` 的稳定化验收。

除非用户重新把其中某项纳入范围，当前开发顺序仅覆盖通用原生参数化能力；不得为了清理范围而删除上述已有实现。

## 8. 审查与语义实体引用

### `scripts/sw_entity_reference.py`

- `geometry_signature`
- `reference_from_metadata`
- `resolve_semantic_reference`
- `create_persistent_reference` / `resolve_persistent_reference`：原生 `GetPersistReference3` 字节引用，可序列化为 Base64；1200 mm² 平面保存重开后保持几何；353 字节边引用与 339 字节顶点引用在另一条边 R2 圆角后及保存重开后均以错误码 0 解析。

用于逐步替代不稳定的 `Face1/Edge1` 和屏幕坐标选择。

### `scripts/sw_review.py`

支持多视图预览、模型摘要、孔段分组、孔位验收、几何测量、报告评分和 Markdown 摘要。报告评分只能发现明显失败，不能替代工程意图审查。

## 9. 当前 Gap

以下能力不能因为 SolidWorks 软件本身支持就宣称项目已稳定支持：

- 椭圆、抛物线、方程式曲线和文本已进入原生能力库并通过真机回归，但尚未加入逐步 Skill CLI；按当前“能力库优先”原则这不是建模阻断；
- 逐步 Skill CLI 的边界特征和复杂曲面；Boundary 封装已完成类型库签名、选择标记和离线契约测试，但 SW2025 `InsertNetBlend` 对原生草图线段的当前组合会终止 SolidWorks，因此已在能力函数内部双门禁，仍属未完成真机能力；基础放样已覆盖 2–16 张完全定义截面的凸台/切除，能力库进一步覆盖 3D 草图导引线、中心线、闭合、薄壁以及法向/方向向量/依附面相切端部约束的凸台/切除放样；UI 的“曲率到面”不在 SW2025 `InsertProtrusionBlend2`/`InsertCutBlend` 公开匹配类型 0..3 中；扫描已覆盖单截面/单路径凸台与切除，能力库进一步覆盖导引线凸台/切除、双向路径、两种常量扭转模式和闭合轮廓薄壁扫描；官方规则不允许实体 Sweep 使用开轮廓，等价需求走原生曲面扫描后加厚，多截面是单个 Sweep 功能但不是当前脚本 API 的标准输入模式；旋转能力库现已覆盖同草图构造线、独立基准轴、外部草图直线经基准轴、实体直边、单/双盲角度、中面、薄壁、到顶点/面/偏置、双向同一/不同引用、盲角与引用混合以及显式多实体作用域；这些高级模式尚未全部加入逐步 Skill CLI，但按“能力库优先”原则不再是原生建模缺口；
- Convert Entities、Offset Entities、显式拾取点 Trim/Extend、草图镜像及线性/圆周草图阵列已进入原生能力库并通过真机回归，但尚未加入逐步 Skill CLI；
- 驱动草图尺寸的原位 COM 身份改绑不受 SW2025 支持：`IAnnotation.SetAttachedEntities` 返回 False；稳定路线是删除—重建并要求调用方替换陈旧引用。该路线现已真机保留驱动值、名称、双向公差与附着实体，不再把可迁移元数据列为缺口。自由点移动、构造状态切换、显式实体删除、选择驱动与 RelationManager 直接关系创建（含失败回滚批处理）、跨既有关系的事务式实体替换和关系完整生命周期均已真机验证；
- 设计表创建/编辑语义；既有设计表只读元数据检查及配置参数矩阵只读检查已实现且不会打开 Excel/OLE，但 `InsertFamilyTableNew/Edit` 属交互式嵌入表格路径，当前不允许在无人值守回归中自动触发；两种 SetParameters 路径在无设计表 SW2025 中未能可靠回写，公共写入继续使用已验证的尺寸、抑制和配置族 API。基础面中心参考点、全部参考点枚举、五种参考轴类型及圆柱/圆锥分支、偏置平面、三点/角度/中面/圆柱相切平行/平行过点/曲线端点法向基准面、数值坐标系、全局变量和尺寸方程式已真机验证；沿曲线参考点→该点处曲线法向基准面的复合原生依赖链，以及曲面相切面上的草图点最近位置/沿草图法向投影均已验证。`OptionOriginOnCurve` 是约束位标志而非独立特征，单独施加于实体直边会返回空；项目已用“曲线上原生参考点 → 通过该点且法向于曲线的基准面”覆盖曲线起点和任意百分比位置的完整用户语义，因此不再把该孤立位标志列为能力缺口；
- 任意特征依赖的直接重新挂接；公开 Feature API 没有通用“改父特征”语义。原生父子依赖递归图、依赖路径、基础独立特征重排、依赖安全重排（父级移到后代之后会在 COM 前阻断）、整个文件夹重排、回滚条、命名 FeatureManager 包含文件夹及两层嵌套文件夹已验证，面/边/顶点持久引用已通过保存重开，边/顶点还通过了另一条边圆角引发的拓扑变化回归；
- 更复杂的多实体分割、互相裁剪和填充曲面曲率连续性；基础 Combine、Intersect、Move/Copy Body、平面/等距/缝合/标准裁剪/接触填充（含内部 3D 约束曲线）/相切填充/法向直纹曲面、Delete Face 全模式、Replace Face 和加厚已真机验证。互相裁剪已完成接口与选择契约，但 SW2025 对正确的曲面体/区域选择仍在 `PostTrimSurface` 返回空，保持 `pilot`。`PostSplitBody2` 会打开交互式“另存为”，公共入口已阻断，内部实验入口采用函数参数与环境变量双门禁，不得自动调用。模具分型、生产级钣金、生产级焊件及齿轮 `pilot` 稳定化已列为暂缓项，不属于当前 Gap 统计。

其中部分存在 Script API 或其他 `pilot` 后端，但没有逐步 Skill CLI 会话保护。需要时应明确选择：使用已有受控脚本并验证、转专项 Skill，或阻断。

## 10. 更新本目录的方法

修改原生能力后同步检查：

1. Skill CLI 的命令帮助；
2. `scripts/sw_part.py`、`sw_hole_features.py`、`sw_document_data.py` 的公共函数；
3. `capabilities.yaml` 的等级、版本和依赖；
4. 单元测试、注册检查和真实临时 Part 回归；
5. 本目录与 `SKILL.md` 是否把“已注册”“已有脚本”“尚未实现”分清。
