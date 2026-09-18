# CH01/CH02 离线标定工具

本工具已实现现场资料准备、ChArUco识别、实测点组装、独立选模/验收和俯视图输出。**目前没有本次现场材料，因此没有新的实测标定，也没有已验证的相机精度。** `field_kit/session.json` 全部保持待填写状态。

## 已经核实的棋盘

原图 `calibration.png`：12列×9行，54个marker（ID 0–53），88个内角点，黑格从左上角开始。`assets/board.json` 保存了原图SHA256、完整ID布局和尺寸。

使用最小兼容字典 **DICT_5X5_100**，DICT_5X5_250/1000的相同前缀也匹配；原始字典容量不可区分。重新生成图与原图的二值像素差为0。以每格6 cm、marker 4.5 cm计算，图案72×54 cm。实物打印比例尚未确认。

## 现场拿什么、做什么

打开 `field_kit/field_sheet.md` 和 `field_kit/proposed_positions.svg`：35个训练位置、12个选模验证位置、12个最终测试位置。它们只是放样建议，需要实测；不把建议坐标复制成“实测”。遇障碍移动点位并记录实际值。每个位置的所有角点和重复画面使用同一集合。

1. 原点A0，x沿40 ft，y沿20 ft；核对边长、对角线和实际覆盖区域。
2. 平整固定棋盘，量横纵各5格（预计30 cm），量板面相对目标地面高度。锥桶仅标位置，不用锥尖作坐标点。
3. 每次对齐原图左上角和长边第二参考点；长边沿+x，短边沿+y。保持8–10秒，人退开。记录有UTC偏移的时间窗口。
4. 两台同时采集；分别补近中远、边缘、接缝两侧的控制/验证/测试点。每个使用区域至少3个独立最终测试位置，每台总数至少12。
5. 拍摄后等实际闭合片段出现，再抽取少量帧检查；远场角点无法辨认就补大而薄的平面十字标记。不要为了让板可见而竖起来后仍称其为地面。

默认只支持地面模型。工具保守拒绝板面偏离地面超过0.2 cm的控制点，不会假装自动补偿高度；此时用薄标记或另行实现实测高度模型。测量不确定度上限2 cm。实际边界可随区域验证结果收紧，不能为了通过验收随意放宽。

## 安装与基本操作

本机已经有隔离环境 `.venv-calibration`。下面从本仓库根目录运行；在分析机安装时使用独立环境，不替换录制环境。

```powershell
$py = '.\.venv-calibration\Scripts\python.exe'
# 新分析环境才需要安装；requirements-tested.txt是本次验证版本
& $py -m pip install -r camera_ground/requirements.txt
& $py -m camera_ground --help
& $py -m unittest camera_ground.test_calibration camera_ground.test_cli -v
```

如需从其他目录的分析程序调用，安装本地包：`python -m pip install -e <本仓库绝对路径>`。只启用包并不会切换任何已有标定。

### 1. 新建现场session

```powershell
& $py -m camera_ground init --board camera_ground/assets/board.json --out calibration_sessions/epoch_202609
```

修改新session的 `session.json`，不要覆盖发放的空模板：

- `session_id`、`geometry_revision`：本次采集与实测场地版本。
- `physical_board_verified=true`、`five_squares_measured_cm=[30,30]`：实际测量。实际比例不同则用 `identify --square-cm ... --marker-cm ...` 重新生成棋盘定义，再开始session。
- 每路 `image_size` / `pixel_transform`：解码后的真实尺寸，顺时针旋转，旋转后裁切，最后缩放到canonical尺寸。默认2160×7680是旧标定方向，**必须检查当前图像**。旋转、裁切不能通过任意缩放代替。
- 每路 `geometry_reviewed=true`、`stitching_settings`：记录实际固件/拼接设置；本工具不改相机设置。
- `valid_from`：本次确认后的带时区时间，如 `2026-09-15T10:30:00-04:00`；不能据此直接批准六月录像。`valid_to`可为空，碰撞后须更新epoch。
- `regions`：在canonical像素坐标画有效多边形和 `exclude_px` 孔洞。接缝若不连续，左右两个region独立训练，中间排除。空多边形会拒绝拟合，不默认全图有效。
- 每次放板填 `measured_origin_cm`、`x_axis_reference_cm`（长边方向上至少20 cm远的实测参考点）、`plane_height_cm`、`plane_verified`、`measurement_uncertainty_cm`、`regions.CH01/CH02`、`zone`（core/edge/seam）、`depth`（near/mid/far）、时间窗口和备注。

每个region至少6个训练位置、3个选模验证位置。分区后数量不够就补点；不要复制同一位置到两个集合。尚未采集的位置保持null，可以留在表里，但不能用于组装。

### 2. 闭合片段抽帧、检测与审核

```powershell
& $py -m camera_ground extract --src 'D:\analysis_inputs\CH01_2026-09-15_10-00-00_to_11-00-00.mp4' --start 125 --window 8 --count 5 --out calibration_sessions/epoch_202609/T11_frames
& $py -m camera_ground observe --session calibration_sessions/epoch_202609/session.json --image calibration_sessions/epoch_202609/T11_frames/frame_00.png --channel CH01 --position T11 --out calibration_sessions/epoch_202609/T11_CH01_f0
```

逐帧查看 `corners.png`，特别检查接缝和强弯曲区域；确认才把对应 `observation.json` 的 `reviewed` 设为true。同一位置重复3–5帧。检测门槛是至少12角点、至少3行3列；多帧使用角点像素中位数，抖动超过3 canonical像素会拒绝。不能只信“检测到了ID”。

抽帧只接受本地明确命名的闭合 `_to_*.mp4`，每次≤30秒、≤5帧，不扫描录像目录、不连RTSP、不读WISER。保存请求偏移及实际PTS，不读整段视频来算哈希。将闭合录像移到分析机需要另行安排，工具不执行批量传输。

手工薄十字标记用 `manual`，命令参数与observe相同，另加 `--points clicks.json`：

```json
{"units":"cm","pixel_space":"canonical","points":[{"id":"cross","pixel":[500,1000],"local_cm":[0,0]}]}
```

local_cm是相对本位置实测原点、沿本位置坐标轴的厘米偏移；单个十字中心就是[0,0]。各实测十字位置有独立position_id及固定split。输出仍需要审核。每个检测来源图像有哈希；同一帧不能重复分配给不同位置。

### 3. 组装、选型、冻结

```powershell
# 用明确的已审核观测文件列表；每台/位置可有多帧
& $py -m camera_ground assemble --session calibration_sessions/epoch_202609/session.json --observations <obs1.json> <obs2.json> --out calibration_sessions/epoch_202609/dataset.json
& $py -m camera_ground fit --dataset calibration_sessions/epoch_202609/dataset.json --channel CH01 --out calibration_sessions/epoch_202609/CH01_fit
& $py -m camera_ground fit --dataset calibration_sessions/epoch_202609/dataset.json --channel CH02 --out calibration_sessions/epoch_202609/CH02_fit
```

每个region比较归一化二阶poly、分片仿射、TPS（正则0、1e-6、1e-4、1e-2、1）。poly每个位置总权重一致；TPS每个位置最多16个最远点采样作为核中心以控制资源，正则按该位置角点数缩放；所有保留验证角点仍参与误差报告。分片仿射插值不使用重复帧增加权重。

部署统一用三角网。poly/TPS在45×45网格加训练点上离散，中心采样偏差>0.5 cm时细化90×90，否则拒绝；这是明确的近似模型，报告的是部署网格的验证误差。三角网逐个检查面积符号和重叠，有孔洞/接缝的三角形必须完整落在有效域内。拒绝翻折、多义、验证点覆盖不全的模型；差距≤1 cm优先分片仿射。

平滑模型不能在接缝上凭空恢复丢失内容。未被训练点包围的范围、被裁掉的边界和接缝均返回NaN及valid=false。选型只用validation；写出原始数据快照、候选比较、验证残差图和不可覆盖的模型文件。

### 4. 一次最终验收

```powershell
& $py -m camera_ground evaluate --dataset calibration_sessions/epoch_202609/dataset.json --model calibration_sessions/epoch_202609/CH01_fit/CH01_calib.json --out calibration_sessions/epoch_202609/CH01_test
& $py -m camera_ground evaluate --dataset calibration_sessions/epoch_202609/dataset.json --model calibration_sessions/epoch_202609/CH02_fit/CH02_calib.json --out calibration_sessions/epoch_202609/CH02_test
```

输出accepted或failed：每台至少12测试位置；每region至少3；core位置平衡RMSE≤10 cm且任何角点误差≤20 cm，edge/seam为≤20/30 cm；逐region、zone验收，报告near/mid/far。角点最大误差标准比仅看每位置平均值更保守。漏测区域不能被全局平均掩盖。

在dataset旁独占写入 `test_usage_CHxx.json` 后，该session不能重新选型或重复验收。若失败后改模型，建立新session并补新的测试位置；旧test可转为validation。锁不防止人复制目录绕过，实验台账仍是最终约束。模型、数据和棋盘保存内容哈希，修改后会拒绝使用。

### 5. 俯视图、合图和跨相机检查

```powershell
& $py -m camera_ground bev --model calibration_sessions/epoch_202609/CH01_test/CH01_calib.json --image <原始参考帧.png> --timestamp '2026-09-15T10:35:00-04:00' --out calibration_sessions/epoch_202609/CH01_bev
& $py -m camera_ground bev --model calibration_sessions/epoch_202609/CH02_test/CH02_calib.json --image <原始参考帧.png> --timestamp '2026-09-15T10:35:00-04:00' --out calibration_sessions/epoch_202609/CH02_bev
& $py -m camera_ground combine --inputs calibration_sessions/epoch_202609/CH01_bev calibration_sessions/epoch_202609/CH02_bev --out calibration_sessions/epoch_202609/combined
& $py -m camera_ground compare --dataset calibration_sessions/epoch_202609/dataset.json --models calibration_sessions/epoch_202609/CH01_test/CH01_calib.json calibration_sessions/epoch_202609/CH02_test/CH02_calib.json --out calibration_sessions/epoch_202609/agreement
```

默认1 cm/像素，1220×610，地面网格像素中心从(0.5,0.5) cm开始，x右/y下；不是1 cm精度声明。透明像素表示无效。逆变换严格使用同一三角网的重心坐标，无另拟合逆多项式。

合图按3个最近验证位置中的最大RMSE排序（保守的局部排名启发式，不是经验证的置信区间），输出来源图：0无效、1 CH01、2 CH02。合图要求相同声明时间与尺度，但**不能由此证明曝光同步**；必须另外用事件/LED确认。多台误差相近不代表真值，compare同时报告各自相对实测点的误差。

`--preview`允许验收前看俯视图，但其元数据明确provisional，不能进入正式合图。动物身体、墙和屋顶不是地面，图中仍会有视差。

## 分析程序接口

```python
from camera_ground.pipeline import GroundCalibration
c = GroundCalibration("<accepted-output>/CH01_calib.json")
xy, valid = c.to_field(points_px, timestamp="2026-09-15T10:35:00-04:00",
                      pixel_transform=c.artifact["pixel_transform"], return_valid=True)
```

调用者必须验证自己的图像处理与声明一致，不能无条件复制metadata。只有在相同方向/裁切下纯缩放的点，才传src_size；缩放采用像素中心约定 `(p+0.5)*scale-0.5`。

`pipeline.to_field(channel, pts_px, config_dir, calib=None, src_size=None, *, timestamp, pixel_transform, return_valid=False)`保留旧入口的前导参数。另有已测试的 `install_analysis_adapter.py` 为相邻分析仓库 `field_coords.py` 增加新类型分支；只有加载新类型才导入本包，旧homography/poly/PnP仍走原实现。新类型要求accepted、显式时间和像素约定，不会自动替换旧JSON。

## 测试与限制

运行 `python -m unittest camera_ground.test_calibration camera_ground.test_cli -v`。16项测试覆盖棋盘重建、单位/板定义篡改、未实测数据、旋转、平面/重复集合、接缝孔洞、翻折重叠、非线性离散反变换、最终测试隔离、失败验收、像素缩放、历史epoch、旧分析入口兼容和俯视透明mask；命令行测试使用临时合成数据，贯通两路拟合、验收、俯视、合图、误差对照和闭合片段抽帧。

现场尚欠：实物格长和高度确认、当前两路图像与拼接设置、实测位置/角点资料、独立测试、真实俯视图。不得将软件合成测试的accepted当成现场accepted。

## 方法依据与适用边界

- [Reolink拼接设置说明](https://support.reolink.com/articles/9156003952025-How-to-Set-up-Image-Stitching-via-Reolink-Software/?slug=duo-2-wifi-duo-floodlight-wifi)：距离影响拼接，可能出现缺失或重影，因此保持设置并单独处理接缝。
- [OpenCV ChArUco检测](https://docs.opencv.org/4.12.0/df/d4a/tutorial_charuco_detection.html)：使用marker身份和局部棋盘角点；全景接缝检测仍需审核。
- [通用相机模型研究及公开实现](https://github.com/puzzlepaint/camera_calibration)：更灵活模型可减少简单参数模型的偏差，但公开实现的近中心初始化与平滑要求不能自动套用于厂商拼接缝。本工具是针对地面任务的可验证工程方案，未声称在Duo 3数据集上获得SOTA成绩。
