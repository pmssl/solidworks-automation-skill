# 高级功能参考

## 目录

- [自定义属性](#自定义属性)
- [设计表与配置](#设计表与配置)
- [钣金设计](#钣金设计)
- [焊件设计](#焊件设计)
- [曲面建模](#曲面建模)
- [仿真/FEA](#仿真fea)

---

## 自定义属性

```python
# 获取属性管理器
# 空字符串 = 文件级属性，配置名 = 配置特定属性
props = model.Extension.CustomPropertyManager("")

# 读取属性
val = ""
resolved = ""
was_resolved = False
is_linked = False
result = props.Get6("Description", False, val, resolved, was_resolved, is_linked)
# resolved 包含解析后的值

# 写入/更新属性
# 类型: 30=文本, 2=数字, 11=Yes/No, 64=日期
props.Add3("Description", 30, "主轴零件 Rev A", 1)  # 1=覆盖
props.Add3("Material", 30, "Steel 1045", 1)
props.Add3("Weight", 2, "2.5", 1)
props.Add3("PartNumber", 30, "PN-001-001", 1)

# 删除属性
props.Delete2("OldProperty")

# 获取所有属性名称
count = props.Count
names = props.GetNames()
```

## 设计表与配置

### 配置管理

```python
from sw_document_data import (
    audit_configuration_rebuilds,
    apply_configuration_family,
    activate_configuration,
    create_configuration,
    feature_suppression_states,
    inspect_configurations,
    set_feature_suppression,
    update_dimension_mm,
)

# 使用官方 AddConfiguration3 创建并激活；默认同名配置幂等复用。
created = create_configuration(
    model,
    "加工",
    comment="CNC 工况",
    alternate_name="MACHINED",
)

# 使用官方 ShowConfiguration2，并以活动配置名回读而非单独 COM 返回值判定。
activated = activate_configuration(model, "加工")

# 用显式 VT_ARRAY|VT_BSTR 写入指定配置，API 内部单位自动换算为米。
dimension = update_dimension_mm(
    model,
    "D1@Boss-Extrude1",
    50.0,
    configuration_mode="specific",
    configuration_names=["加工"],
)

evidence = inspect_configurations(model)

# 逐配置强制重建并回读特征错误、实体数量、体积和包络；不保存并恢复原活动配置。
audit = audit_configuration_rebuilds(model)

# 只在“加工”配置抑制指定特征；函数会逐配置激活并回读真实抑制状态。
suppression = set_feature_suppression(
    model,
    "Cut-Extrude1",
    "suppress",
    configuration_mode="specific",
    configuration_names=["加工"],
)
```

SW2026 真机已验证配置创建、切换、配置级尺寸/属性以及保存重开回读。`AddConfiguration3`
会自动激活新配置，因此重复调用 `ShowConfiguration2` 可能返回 `False`；执行器会记录原始
返回值，但以 `ConfigurationManager.ActiveConfiguration.Name` 回读和重建结果作为成功证据。
配置级特征抑制已用三配置实体体积和 `IFeature.IsSuppressed` 真机回读验证。
批量配置族可直接使用 `apply_configuration_family`，每个配置条目可同时给出
`dimensions_mm`、`properties` 和 `feature_suppression`；调用只使用原生配置作用域，
不会打开 Excel 或保存文件。显示状态清单、创建、激活、重命名和非活动状态删除已由
`inspect_display_states` / `create_display_state` / `activate_display_state` /
`rename_display_state` / `delete_display_state` 真机验证。派生配置通过
`create_derived_configuration` 创建，并由 `configuration_hierarchy` 回读父子层级；两级层级已真机验证。
`rename_configuration` 使用可写的 `IConfiguration.Name` 并验证整个父子图；
`delete_configuration` 遵守活动配置不可删除的原生限制，必要时先切换到保留配置，默认禁止
隐式级联，显式 `include_descendants=True` 时按叶到根顺序删除。两级派生子树的重命名、
活动孙配置切换和完整删除已真机验证，前后实体包络不变。
`inspect_configuration_properties` / `update_configuration_properties` 读取和更新配置备注、
说明、备用名称、备用名称/说明 BOM 显示开关以及“抑制新特征”。后者仅对非活动配置生效，
封装会按需临时切换并恢复；真机以新增贯穿切除的抑制状态和实体体积证明行为生效。
`BOMPartNoSource` 在 SW2025 的动态和强类型 property-put 均不生效，只提供只读结果。
`audit_configuration_rebuilds` 已在 SW2025 的 80×50 mm、12/6/20 mm 三配置族上真机验证：
逐配置 `ForceRebuild3(False)` 后 `NeedsRebuild=False`，每个配置均为单实体、零顶层特征错误，
体积为 48000/24000/80000 mm³，包络深度与配置尺寸一致，并恢复原活动配置；该检查不保存文件。
`read_configuration_parameters(model, configuration_name)` 可只读枚举单个配置的尺寸、
特征抑制和元数据参数；50×30×6 mm 配置已由矩阵值、`IDimension` 和 B-Rep 深度三重验证。
未添加设计表时，SOLIDWORKS 官方说明返回值可能不准确，因此函数会设置
`review_required=true`，调用方仍须回读真实尺寸、抑制状态和几何。
设计表创建/编辑仍是 `pilot` 范围外能力。

对已有设计表，只读检查使用 `inspect_design_table(model)`；它不会激活表格或打开 Excel，
并兼容无设计表时 `GetDesignTable()` 返回非空占位代理、范围值为 `-2` 的行为。
`IConfiguration.SetParameters` 与 `IConfigurationManager.SetConfigurationParams` 在 SW2025
无设计表配置上均未能可靠回写真实尺寸，因此不作为公共写入入口；使用
`update_dimension_mm`、`set_feature_suppression` 和 `apply_configuration_family`。

### 设计表

```python
# 插入设计表（从 Excel）
design_table = model.InsertFamilyTableOpen(excelFilePath)

# 编辑完成后关闭
model.CloseFamilyTable()

# 更新设计表
model.InsertFamilyTableEdit()
```

## 钣金设计

> 范围说明（2026-11-19）：保留以下现有 `pilot` 实现与使用参考；生产级钣金专项能力暂缓开发和稳定化验收，不计入当前剩余原生能力。

### 基本操作

```python
from sw_sheet_metal import BaseFlangeSpec, create_base_flange

# 先创建并退出开放或闭合草图，再使用现代 FeatureData API。
feature = create_base_flange(
    model,
    sketch_name,
    BaseFlangeSpec(
        thickness=0.002,
        bend_radius=0.0025,
        depth=0.100,
        k_factor=0.42,
    ),
)
```

该封装使用 `CreateDefinition(swFmBaseFlange)`、`IBaseFlangeFeatureData.Initialize`
和 `CreateFeature`，不会猜测已废弃长参数接口。SW2026 SP01.1 已验证开放 U 型轮廓、
两道真实折弯及保存重开；边线法兰、斜接法兰和放样折弯仍按 `pilot` 门禁处理。

### 展开图导出

```python
from sw_export import export_flat_pattern_dxf

# 零件必须先保存；选项位掩码默认为“展开几何(1) + 折弯线(4)”。
export_flat_pattern_dxf(model, dxfPath, include_bend_lines=True)
```

`ExportToDWG2` 的第五个参数是 12 个双精度数值组成的对齐数组，第八个参数才是
钣金选项位掩码；不要把多个布尔值误当作“轮廓/折弯线/草图/隐藏边线”。

### 钣金参数

```python
# 获取钣金特征数据
feat = model.FeatureByName("Sheet-Metal1")
sheet_metal_data = feat.GetDefinition()
thickness = sheet_metal_data.Thickness    # 板厚
bend_radius = sheet_metal_data.BendRadius # 折弯半径
```

## 焊件设计

> 范围说明（2026-11-19）：保留以下现有 `pilot` 实现与使用参考；生产级焊件专项能力暂缓开发和稳定化验收，不计入当前剩余原生能力。

### 切割清单

```python
from sw_weldment import (
    create_structural_member,
    ensure_cut_list,
    export_cut_list_csv,
    set_cut_list_properties,
    weldment_evidence,
)

member = create_structural_member(
    model,
    profile_path,
    [sketch_segments],
    apply_corner_treatment=True,
)
ensure_cut_list(model)
set_cut_list_properties(model, {"PROFILE_DESIGNATION": "HSS1x1x16ga"})
evidence = weldment_evidence(model)
export_cut_list_csv(evidence, csv_path)
```

SW2026 的 `InsertWeldmentCutList2` 在 Python IDispatch 下可能被投影成值为
`None` 的伪属性；封装会按本机类型库确认的 DISPID 174 以
`DISPATCH_METHOD` 调用。矩形框架回归会按实体包围盒最长边分组，生成两个
真实 `CutListFolder`，而不是把不同长度构件错误合并。

### 结构构件

```python
from sw_weldment import create_weldment_profile

# 型材文档中先完成并退出闭合轮廓草图；可写入型材/BOM 来源属性。
profile = create_weldment_profile(
    profile_model,
    profile_sketch,
    profile_path,
    properties={"DESCRIPTION": "HSS1x1x16ga", "MATERIAL": "steel_a500b"},
)
```

`create_structural_member()` 内部使用 `CreateStructuralMemberGroup` 与最新
`InsertStructuralWeldment5`，路径段和组均作为 `VT_ARRAY | VT_DISPATCH`
安全数组封送；调用者不需要猜长参数或依赖当前选择集。

## 曲面建模

```python
# 拉伸曲面
feature_mgr.InsertExtrudedSurface(depth, flip, dir, t1, t2, d1, d2)

# 旋转曲面
feature_mgr.InsertRevolvedRefSurface(...)

# 放样曲面
feature_mgr.InsertLoftRefSurface2(...)

# 扫描曲面
feature_mgr.InsertSweepRefSurface(...)

# 平面区域
feature_mgr.InsertPlanarRefSurface()

# 修剪曲面
feature_mgr.InsertTrimSurface2(...)

# 缝合曲面
feature_mgr.InsertSewRefSurface(True, False, 0.001)

# 曲面加厚为实体
feature_mgr.InsertThickenSheet(thickness, False, True)
```

## 仿真/FEA

> 需要安装 SolidWorks Simulation 插件

```python
# 获取 Simulation 插件
cos_works = sw.GetAddInObject("SldWorks.Simulation")
if not cos_works:
    print("Simulation 插件未安装或未激活")

study_mgr = cos_works.StudyManager

# 创建静态分析算例
study = study_mgr.CreateStudy(
    model,
    "StaticStudy1",
    0  # 0=Static, 1=Frequency, 2=Buckling, 3=Thermal, 5=Fatigue
)

# 添加材料（通过 SolidBody）
# 添加约束（Fixed, Roller/Slider, Prescribed）
# 添加载荷（Force, Pressure, Gravity, Torque）

# 运行分析
study.RunAnalysis()

# 获取结果
results = study.Results
# 应力、位移、安全系数等
```

### 算例类型

| 值 | 类型 | 说明 |
|---|---|---|
| 0 | Static | 静态分析 |
| 1 | Frequency | 频率分析 |
| 2 | Buckling | 屈曲分析 |
| 3 | Thermal | 热分析 |
| 4 | Drop Test | 跌落测试 |
| 5 | Fatigue | 疲劳分析 |
| 6 | Nonlinear | 非线性分析 |
