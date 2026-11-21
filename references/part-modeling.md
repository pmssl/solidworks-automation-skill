# 零件建模 API 参考

## 草图操作

### 基准面选择

```python
# 英文版
model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
# 中文版
model.Extension.SelectByID2("前视基准面", "PLANE", 0, 0, 0, False, 0, None, 0)
```

基准面对应关系：
| 英文 | 中文 | 法线方向 |
|---|---|---|
| Front Plane | 前视基准面 | Z 轴 |
| Top Plane | 上视基准面 | Y 轴 |
| Right Plane | 右视基准面 | X 轴 |

### 草图几何体方法速查

| 方法 | 参数 | 说明 |
|---|---|---|
| `CreateLine(x1,y1,z1, x2,y2,z2)` | 起点终点坐标（米） | 直线 |
| `CreateCircleByRadius(cx,cy,cz, r)` | 圆心+半径 | 圆 |
| `CreateCenterRectangle(cx,cy,cz, rx,ry,rz)` | 中心+角点 | 中心矩形 |
| `CreateCornerRectangle(x1,y1,z1, x2,y2,z2)` | 对角点 | 角点矩形 |
| `CreateArc(cx,cy,cz, x1,y1,z1, x2,y2,z2, dir)` | 圆心+起终点+方向 | 圆弧 |
| `CreatePolygon(cx,cy,cz, sx,sy,sz, sides, inscr)` | 中心+顶点+边数 | 正多边形 |
| `CreateEllipse(cx,cy,cz, mx,my,mz, r)` | 中心+长轴端点+短轴半径 | 椭圆 |
| `CreateSpline2(pointArray, closed)` | 点数组+是否闭合 | 样条曲线 |
| `CreateSketchSlot(type, w, w, ...)` | 类型+宽度+端点 | 槽口 |

### 草图约束

```python
# 选中实体后添加约束
model.SketchAddConstraints("sgHORIZONTAL")
```

常用约束类型：`sgFIXED`, `sgHORIZONTAL`, `sgVERTICAL`, `sgCOLINEAR`, `sgPARALLEL`, `sgPERPENDICULAR`, `sgTANGENT`, `sgCONCENTRIC`, `sgEQUAL`, `sgSYMMETRIC`, `sgMIDPOINT`, `sgCOINCIDENT`

### 草图选择稳定策略

优先使用 `sw_part.sketch()` 上下文或 `end_sketch()` 返回值，不要手写 `SelectByID2("Sketch1", "SKETCH", ...)` 作为唯一选择方式。SolidWorks 2024 中文版反馈过 SKETCH 名称选择持续返回 `False` 的情况。

推荐：

```python
with sketch(model, "Front Plane") as sketch_name:
    sketch_circle(model, 0, 0, mm(25))
feature = extrude_boss(model, sketch_name, mm(50))
```

手动流程：

```python
start_sketch(model, "Front Plane")
sketch_circle(model, 0, 0, mm(25))
sketch_ref = end_sketch(model)
feature = extrude_boss(model, sketch_ref, mm(50))
```

内部规则：`extrude_boss()` / `extrude_cut()` 会按“活动草图引用 -> 创建时缓存引用 -> FeatureByName -> SelectByID2("SKETCH")”顺序选择草图；不再把残留选择集当作草图已选中的证据。

## 特征操作

### 原生缩放特征

```python
from sw_part import scale_feature, scale_feature_evidence

# 以模型原点进行非均匀 XYZ 缩放。
feature = scale_feature(model, 1.5, 0.5, 2.0, about="origin")
evidence = scale_feature_evidence(feature)

# 只提供一个因子时，以质心进行均匀缩放。
uniform = scale_feature(model, 0.5, about="centroid")

# 以原生坐标系为中心缩放，并可限制到显式实体子集。
coordinate_scale = scale_feature(
    model, 2.0, about="coordinate_system",
    coordinate_system=coordinate_system_feature,
    bodies=(body,),
)
```

该入口创建可抑制、可回滚的 FeatureManager `Scale` 历史特征，不修改前序草图和尺寸。
`selected_body_count=0` 表示没有显式实体子集，即缩放当前全部实体；非零值表示选定实体范围。`about="coordinate_system"` 必须传入原生坐标系特征，证据中的 `coordinate_system` 会回读其名称；其他中心模式不得混入该引用。
交付时必须用 `IScaleFeatureData` 因子、包络尺寸、体积、特征错误码和重建结果交叉验证。

### 原生圆顶特征

```python
from sw_part import dome_feature, dome_feature_evidence, update_dome_feature

dome = dome_feature(
    model,
    faces=(planar_face,),
    height=0.008,
    reverse_direction=False,
    elliptical=False,
)
evidence = dome_feature_evidence(dome, model)

# 可原位修改高度、凹凸方向、椭圆模式、约束点/草图或显式方向边。
update_dome_feature(
    dome, model,
    constraint=sketch_point_3d_entity,
    direction=linear_edge,
)
```

该入口调用原生 `IModelDoc2.InsertDome` 并保留 FeatureManager 历史。面选择使用官方要求的 mark 1；`faces` 可包含一个或多个面。`IDomeFeatureData2` 在读取或修改面、约束和方向引用前需要 `AccessSelections`，两个辅助函数会自动获取并释放选择访问。约束点/草图会取代固定距离控制：SW2025 真机中加入约束点后 `Height` 归零，并清除此前设置的显式方向，这是 SolidWorks 的定义归一化结果，调用方必须分步回读而不能假设二者同时保留。曲面体的 `IBody2.GetBodyBox` 是近似包围盒，不能用其极值代替精确圆顶高度；高度、反向和椭圆标志必须从 FeatureData 回读，并结合体积变化、错误码和重建结果验收。

### 原生压凹与压印切除

```python
from sw_part import indent_feature, indent_feature_evidence

indent = indent_feature(
    model,
    target_body=target_body,
    tool_regions=(tool_body_face,),
    thickness=0.002,
    clearance=0.001,
    exclude_selected_regions=True,
    clearance_direction=True,
    cut=False,
)
evidence = indent_feature_evidence(indent, model)
```

目标实体必须用 mark 1，工具实体区域用 mark 4。`IBody2` 与面/边的选择接口不同：目标 Body 必须走 `Select2(Append, ISelectData)`，工具面通常走 `Select4`。Cut 模式仍必须给旧式 `InsertIndent` 传入正的 `thickness` 占位值；SW2025 传 0 会在选择正确时静默返回空。曲面工具应传它的面区域而不是整个 `SurfaceBody`：同一张完整覆盖目标的 X=5 mm 平面，以整个曲面体 mark 4 选择时 `InsertIndent` 返回空，改传单个面区域后创建成功。`cut_direction=False/True` 分别保留 X=5…30 / -30…5 mm 半空间，体积 10000/14000 mm³，之和等于原目标 24000 mm³。

### 原生 Flex 变形

```python
from sw_part import flex_feature, flex_feature_evidence

# 沿 Z 长轴弯曲：rotation=X、tangent=Y、radius=Z。
bend = flex_feature(
    model, body, "bending", math.radians(30),
    rotation_axis=(1, 0, 0), tangent_axis=(0, 1, 0), radius_axis=(0, 0, 1),
    left_trim=0.040, right_trim=0.040,
)

# 绕 Z 长轴扭转：rotation=Z。
twist = flex_feature(
    model, body, "twisting", 0.2,
    rotation_axis=(0, 0, 1), tangent_axis=(1, 0, 0), radius_axis=(0, 1, 0),
    left_trim=0.040, right_trim=0.040,
)

# 沿 Z 长轴锥化/拉伸：tangent=Z；第三轴取 -Y 以保持右手系。
stretch = flex_feature(
    model, body, "stretching", 0.2,
    rotation_axis=(1, 0, 0), tangent_axis=(0, 0, 1), radius_axis=(0, -1, 0),
    left_trim=0.040, right_trim=0.040,
)
evidence = flex_feature_evidence(stretch, model)
```

Flex 实体必须通过 `Body2.Select2(Append, ISelectData)` 使用 mark 1；官方 `InsertFlexFeature` 页面没有写出该标记，但 SW2025 的 mark 0 会稳定返回空。`left_trim/right_trim` 是从两侧各自量取的非负距离，可以相等；不得传成 `-left/+right` 世界坐标。三组轴会归一化并要求两两正交，但其角色必须与目标实体方向一致：弯曲主要沿 radius 轴、扭转绕 rotation 轴、锥化和拉伸沿 tangent 轴。`amount` 直接传给旧式 API 的 `Angle` 参数；弯曲、扭转、锥化按弧度回读，拉伸会被 SW2025 归一化为显示尺寸 `D0` 中的实际轴向距离。例如原始输入 `0.2` 在当前 100 mm 用例中回读 `D0=5.092958 mm`，并与 Z 包络增量一致，不能把原始 `0.2` 当作 0.2 m 或最终拉伸长度。SolidWorks 2025 没有公开 Flex FeatureData，且四种模式的 `GetTypeName2` 都返回家族类型 `Bending`；验收必须同时检查调用枚举、D0、错误码、重建、单实体、包络和体积语义，不能用类型名区分四种模式。

### 原生直纹曲面五模式

```python
from sw_part import ruled_surface_from_edges, ruled_surface_evidence

tangent = ruled_surface_from_edges(model, boundary_edge, 0.010, surface_type=0)
normal = ruled_surface_from_edges(model, boundary_edge, 0.010, surface_type=1)
tapered = ruled_surface_from_edges(
    model, boundary_edge, 0.010, surface_type=2,
    angle_rad=math.radians(20), direction_references=(direction_edge,),
)
perpendicular = ruled_surface_from_edges(
    model, boundary_edge, 0.010, surface_type=3,
    direction_references=(direction_edge,),
)
swept = ruled_surface_from_edges(
    model, boundary_edge, 0.010, surface_type=4,
    direction_vector=(0, 0, 1),
)
evidence = ruled_surface_evidence(swept, model)
```

创建方法使用 0–4，而 `IRuledSurfaceFeatureData.Type` 回读一位偏移后的枚举 1–5。SW2025 的 XYZ 参数只可靠定义 Sweep 数值向量；锥化和垂直向量模式必须先创建有效法向种子，再通过强类型 FeatureData 的 `SetDirectionReference` 原位切换。公共入口已封装该过程并拒绝零向量、缺失引用以及把数值向量误用于类型 2/3。40 mm 边、10 mm 距离的五模式回归均新增 400 mm² 曲面；20°锥化的横向/法向投影为 9.397/3.420 mm，全部错误码 0且重建成功。

### 原生放样曲面的导引线、中心线与方向约束

```python
from sw_part import loft_surface, loft_surface_evidence

guided = loft_surface(model, (profile1, profile2), guide_curves=(guide3d,))
centered = loft_surface(model, (profile1, profile2), centerline=centerline3d)
directed = loft_surface(
    model, (profile1, profile2),
    start_matching_type=2, end_matching_type=2,
    start_tangent_reference=axis, end_tangent_reference=axis,
)
evidence = loft_surface_evidence(directed, model)
```

选择角色严格为截面 mark 1、导引线 mark 2、中心线 mark 4、起点方向 mark 8、终点方向 mark 32；类型 2 必须同时提供相应方向引用，类型 0/1/3 不得夹带方向引用。SW2025 的 `BlendRefSurface` 虽能创建、重建并保留父依赖，但 `IFeature.GetDefinition` 返回空，因此不能把实体 Loft 的 `ILoftFeatureData` 回读能力套到曲面 Loft。验收使用特征类型、错误码、父依赖与几何变化交叉证明：750 mm² 无约束基线经弯曲导引线、弯曲中心线和 Y 向起止方向轴后分别变为 823.668、823.523 和 842.538 mm²。`loft_surface_evidence()` 会明确返回 `feature_data_available=false`，不会从请求参数伪造 FeatureData。

### 原生扫描曲面的导引线与常量扭转

```python
from sw_part import sweep_surface, sweep_surface_evidence

guided = sweep_surface(
    model, profile, path,
    guide_curves=(guide,), twist_control=2,
)
twisted = sweep_surface(
    model, profile, path,
    twist_control=8, twist_angle=math.pi / 2,
)
evidence = sweep_surface_evidence(twisted, model)
```

官方选择角色为 profile mark 1、guide mark 2、path mark 4。导引线不允许与双向 `direction=1` 或常量扭转 `twist_control=8/9` 同时使用，公共入口会在 COM 调用前阻断。SW2025 真机以 20×40 mm 基线验证：跟随第一导引线（类型 2）回读 1 条 guide，面积变为 660 mm²；无 guide 的 90° 常量扭转（类型 8）精确回读 π/2，曲面面积 820.027 mm²并产生 20 mm Z 跨度。两者均为单曲面体、错误码 0且重建成功。

### 原生延伸曲面三种终止条件

```python
from sw_part import extend_surface, extend_surface_distance

same = extend_surface_distance(model, boundary_edge, 0.010, linear=False)
linear = extend_surface_distance(model, boundary_edge, 0.010, linear=True)
to_point = extend_surface(
    model, boundary_edge, end_condition=1,
    terminal_reference=sketch_point,
)
to_face = extend_surface(
    model, boundary_edge, end_condition=2,
    terminal_reference=solid_face,
)
```

终止条件 0 使用正距离且禁止终止引用；条件 1/2 必须提供点或实体面且禁止非零距离。官方 API 的“到面”只支持实体面，不接受曲面体面。SW2025 的 FeatureData `Type` 映射为 `0=Linear`、`1=Same Surface`，与 `InsertExtendSurface(ExtendLinear, ...)` 的布尔直觉顺序相反。40×30 mm 平面曲面四案均从 1200 增至 1600 mm²，回读单选择项、对应 Type/EndCondition、错误码 0并重建成功。

### 原生曲面展平

```python
from sw_part import flatten_surface, flatten_surface_evidence

flattened = flatten_surface(
    model, curved_face, anchor_vertex,
    accuracy_factor=3, use_tears=False,
)
evidence = flatten_surface_evidence(flattened, model)
```

待展平面使用 mark 1，锚点顶点使用 mark 16；精度范围是 1–10，1 为最高精度。SW2025 以 R10×20 mm、270°圆柱片验证：源面积 942.477796 mm²，精度 3 的展开面积 942.466823 mm²，误差约 0.00116%；特征保留源曲面和展开曲面两个曲面体。FeatureData 回读一个面、有效锚点、无 guide/tear/map edge、错误码 0且重建成功。高级 relief cuts、guide edges 和 map edges 尚需各自的选择角色与几何回归，不能由基础展平结果外推。

### FeatureExtrusion3 参数详解

```python
feature_mgr.FeatureExtrusion3(
    Sd,           # bool: 单方向（True）或双方向（False）
    Flip,         # bool: 翻转切割方向
    Dir,          # bool: 翻转挤出方向
    T1,           # int: 终止条件1 (见下表)
    T2,           # int: 终止条件2（双方向时使用）
    D1,           # float: 深度1（米）
    D2,           # float: 深度2
    Dchk1,        # bool: 拔模1
    Dchk2,        # bool: 拔模2
    Ddir1,        # bool: 拔模方向1向外
    Ddir2,        # bool: 拔模方向2向外
    Dang1,        # float: 拔模角度1（弧度）
    Dang2,        # float: 拔模角度2
    OffsetReverse1, # bool: 偏移反转1
    OffsetReverse2, # bool: 偏移反转2
    TranslateSurface, # bool: 平移曲面
    Merge,        # bool: 合并结果
    UseFeatScope, # bool: 自动选择实体范围
    UseAutoSelect, # bool: 自动选择
    T0,           # bool:
    StartOffset   # float: 起始偏移
)
```

终止条件枚举：
| 值 | 名称 | 说明 |
|---|---|---|
| 0 | swEndCondBlind | 给定深度 |
| 1 | swEndCondThroughAll | 完全贯穿 |
| 2 | swEndCondThroughAllBoth | 两侧贯穿 |
| 5 | swEndCondUpToSurface | 成形到一曲面 |
| 6 | swEndCondMidPlane | 两侧对称 |
| 7 | swEndCondUpToBody | 成形到实体 |

### FeatureCut4 参数详解

与 FeatureExtrusion3 类似，但用于切除操作。额外参数：
- `NormalCut`: 法向切除
- `FlipSide`: 翻转切除侧

### FeatureRevolve2 参数

```python
feature_mgr.FeatureRevolve2(
    SingleDir,     # bool: 单方向
    IsSolid,       # bool: 实体旋转（True）
    IsThin,        # bool: 薄壁旋转
    IsCut,         # bool: 切除旋转
    ReverseDir,    # bool: 反转方向
    BothDirectionUpToSameEntity, # bool
    Dir1Type,      # int: 终止条件（0=Blind）
    Dir2Type,      # int
    Dir1Angle,     # float: 旋转角度（弧度）
    Dir2Angle,     # float
    OffsetReverse1, # bool
    OffsetReverse2, # bool
    OffsetDistance1, # float
    OffsetDistance2, # float
    ThinType,      # int: 薄壁类型
    ThinThickness1, # float
    ThinThickness2, # float
    Merge,         # bool
    UseFeatScope,  # bool
    UseAutoSelect  # bool
)
```

### 阶梯轴建模推荐流程

轴类零件优先用“半剖轮廓 + 中心线 + 旋转凸台”一次生成主体，不要逐段拉伸圆柱再合并。这样特征树更短，轴肩位置和总长也更容易由参数表控制。

推荐做法：

1. 用毫米参数表描述轴段：`start_mm`、`end_mm`、`diameter_mm`。
2. 在 `Front Plane` 上画中心线作为旋转轴。
3. 按轴段半径生成一条闭合半剖轮廓。
4. 调用 `FeatureRevolve2(..., 2*pi, ...)` 后立即检查返回特征不是 `None`。
5. 将公差、形位公差、粗糙度作为工程要求记录到属性或交付说明，不要直接扰动名义实体尺寸。

最小模式：

```python
segments = [
    {"start": 0, "end": 43, "diameter": 56},
    {"start": 43, "end": 113, "diameter": 65},
]

with sketch(model, "Front Plane") as sketch_name:
    model.SketchManager.CreateCenterLine(mm(-5), 0, 0, mm(120), 0, 0)
    points = [(0, 0), (0, 28), (43, 28), (43, 32.5), (113, 32.5), (113, 0), (0, 0)]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        model.SketchManager.CreateLine(mm(x1), mm(y1), 0, mm(x2), mm(y2), 0)

model.ClearSelection2(True)
model.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
feature = model.FeatureManager.FeatureRevolve2(
    True, True, False, False, False, False,
    0, 0, 2 * math.pi, 0,
    False, False, 0, 0, 0, 0, 0,
    True, True, True,
)
if feature is None:
    raise RuntimeError("阶梯轴旋转主体创建失败")
```

### 圆柱表面长圆槽

图纸中的键槽、长圆槽、局部沉槽如果位于圆柱外表面，不要直接在中心基准面上切除。中心面切除容易把轴“剖开”，预览看起来像大平面开口，而不是表面凹槽。

稳定做法：

1. 按槽所在圆柱半径创建平行于 `Front Plane` 的偏置参考面，偏置量约等于目标圆柱半径。
2. 在该切向参考面上用 `sketch_slot()` 画长圆槽。
3. 用盲切深度表达槽深；先尝试一个方向，失败再翻转 `flip`。
4. 创建成功后隐藏临时参考面，避免预览图被橙色基准面干扰。

```python
plane = model.FeatureManager.InsertRefPlane(8, mm(radius_mm), 0, 0, 0, 0)
plane.Name = "Plane_Keyway_Tangent"

model.Extension.SelectByID2(plane.Name, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
model.SketchManager.InsertSketch(True)
sketch_name = model.SketchManager.ActiveSketch.Name
sketch_slot(model, mm(x1), 0, mm(x2), 0, mm(slot_width_mm / 2))
model.SketchManager.InsertSketch(True)

feature = extrude_cut(model, sketch_name, mm(depth_mm), direction=True, flip=True)
if feature is None:
    feature = extrude_cut(model, sketch_name, mm(depth_mm), direction=True, flip=False)
if feature is None:
    raise RuntimeError("圆柱表面长圆槽创建失败")
```

注意：`CreateSketchSlot` 参数中 `radius` 是槽宽相关参数，实际表现需用局部测试验证。对制造精确槽宽要求高时，导出后用测量或工程图复核。

### 圆角/倒角

```python
# 圆角 FeatureFillet 参数
feature_mgr.FeatureFillet(
    Options,   # int: 195 = 常用默认值
    R1,        # float: 半径（米）
    R2,        # float: 第二半径
    R3,        # float: 第三半径
    Rarray1,   # variant: 半径数组1
    Rarray2,   # variant: 半径数组2
    Rarray3    # variant: 半径数组3
)

# 倒角 InsertFeatureChamfer
feature_mgr.InsertFeatureChamfer(
    Options,     # int: 4 = 角度距离
    ChamferType, # int: 1 = 等距离
    Width,       # float: 距离（米）
    Angle,       # float: 角度（弧度）
    OtherDist,   # float: 另一距离
    VertexDist1, # float
    VertexDist2, # float
    VertexDist3  # float
)
```

### 圆角/倒角当前可靠边界

圆角和倒角的核心难点不是 API 参数本身，而是**稳定选择目标边线/面**。不同 SolidWorks 版本、界面语言、特征顺序和草图轮廓都会改变自动命名的 `Edge`/`Face`，因此不要把“随机坐标 SelectByID2 选边 + FeatureFillet”当成高可靠流程。

推荐策略：

1. 基准 demo 和无人值守批量脚本不要把圆角/倒角作为成功标准。
2. 需要圆角时，优先在建模阶段用更稳定的草图轮廓近似，例如圆弧、槽口、圆角矩形草图。
3. 必须做特征圆角/倒角时，先通过 body/face/edge 枚举按几何条件过滤目标边，再选择实体对象调用特征，不要依赖临时的 `Edge1` 名称。
4. 圆角失败应降级为保留直边模型，并在审查报告或最终说明中标注“外观圆角未应用”，不要让模型生成流程整体失败。

## SelectByID2 实体类型

| 类型字符串 | 说明 |
|---|---|
| `"PLANE"` | 基准面 |
| `"FACE"` | 面 |
| `"EDGE"` | 边线 |
| `"VERTEX"` | 顶点 |
| `"SKETCH"` | 草图 |
| `"BODYFEATURE"` | 实体特征 |
| `"COMPONENT"` | 组件 |
| `"AXIS"` | 轴线 |
| `"SKETCHSEGMENT"` | 草图线段 |
| `"SKETCHPOINT"` | 草图点 |
| `"EXTSKETCHSEGMENT"` | 外部草图线段 |
| `"REFERENCECURVES"` | 参考曲线 |
