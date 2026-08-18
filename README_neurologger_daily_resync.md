# Neurologger (CE64X / WILD) 每日 Resync 协议

**目的**:logger 平时一直在自己的 SD 卡上连续录制,但它的板载时钟会和主 PC 时间越差越远
(实测:一台差 12 分 43 秒,另一台差 58 分 34 秒)。每天做一次 reset + resync,把设备 RTC
重新锚定到主 PC 时间,保证电生理数据能和相机视频 / PC 时间对齐;同时也清掉 device 卡死、
BLE 反复 reconnect 之类的积累状态。

**版本依据**:wild_console 3.4.2.132(2026-08-17 反编译确认的机制,见文末"原理"一节)。

---

## 每日流程(每天固定时间做一次,每台 logger 依次做)

**用主 PC 做,不要用 mini PC**(主 PC 天线信号强;mini PC 信号太弱,连接慢、容易断)。

1. **连接**:打开 wild_console,在 Device List 选中目标 logger,点 **Connect**。
2. **连上瞬间立刻点 Reset device**(每天例行,不管连接快慢都 reset):
   - 如果连接超过 **60 秒**还没连上,或连上后总是自动 reconnect —— 说明 device 卡了,
     更要在连上的瞬间马上点 reset。
   - Reset 会让设备重启并**停止当前录制**(会产生每天一次的短暂录制间隙,属于预期)。
3. **等待重连稳定**:reset 后设备重启、重新广播,console 重连。等状态栏 **`Cmd:` 计数涨到
   ≥ 256** 再进行下一步(此时 RTC 写入 0x8A、初始对时 `Sync[InitTrain]` 都已自动完成,
   遥测心跳稳定)。
4. **检查对时**:状态栏应出现 **`Sync[Live]`**,健康标准:
   - `dev=00:00.0xx`(分:秒.毫秒,应接近 0)
   - `err=±几毫秒`,**不能是** `err=outlier(...)`,也不能是几百毫秒/几秒级
   - 不达标 → 点 **Resync**;还不行 → 再 reset 一次,从第 3 步重来。
5. **点 Record Start**,确认真的开录了:
   - **Recording time 从 00:00 开始走、Storage Used(MB) 在涨** = 已在录制。
   - 如果 States 显示 `record start failed:` 但上面两项都在动 → 是 BLE ack 超时的假报警,
     忽略即可(确认已开录后,设备会通过 rec-time 流补确认)。
   - 如果 Recording time 不走 → 再点一次 Record Start。
6. **记录到每日表格**(见下),然后 **Disconnect**,让设备继续自己录。

---

## 每日记录表

| 日期 | 时间 | 设备 ID | reset 前 dev 值 | resync 后 err | 电压(V) | Storage(MB) | 备注 |
|------|------|---------|----------------|---------------|---------|-------------|------|
|      |      | CE64X_CACB6D600151 |     |               |         |             |      |
|      |      | CE64X_A7F8EDC4A051 |     |               |         |             |      |

> **`reset 前 dev` 必须记**:它就是前一天那段录制相对 PC 时间的时钟偏差,事后对齐
> 前一天的数据全靠这个数。reset 之后这个偏差信息在设备上就没有了。

---

## 故障处理速查

| 现象 | 处理 |
|------|------|
| Connect 超过 60 秒 | 断开重连;连上的瞬间马上点 reset |
| 连上后反复 reconnect | device 卡了 —— 连上瞬间马上 reset |
| reset 后 `Sync[Live]` 仍是 outlier 或误差很大 | 先检查主 PC 时间对不对(time.is),再点 Resync / 再 reset |
| `record start failed:` 但 Recording time 在走、Storage 在涨 | 假报警,忽略 |
| `record start failed:` 且 Recording time 不走 | 再点 Record Start;仍失败则 reset 后重来 |

---

## 自动监控(2026-08-18 起)

`neurologger_alive_check.ps1`(SYSTEM 任务,每 5 分钟)读取 wild_console 持续刷新的
`C:\Users\Cornell\AppData\Local\CE32_console\discovered_devices.csv`,某台 logger
超过 60 分钟没被 BLE 听到就发 Slack 告警(附手机排查步骤);CSV 本身超过 15 分钟没
更新(console 被关掉)也会告警。低电量(<3.60 V)和存储(≥90%)各有一次性提醒。
详见 `change_log/2026-08-18-neurologger-alive-check.md`。
**前提:主 PC 上 wild_console 必须保持开着并在扫描** —— 这现在是 rig 的一部分。

## 原理(为什么这样做,来自 3.4.2.132 反编译)

- 连接建立后 console 自动发 **RTC push (0x8A)** 把主机时间写进设备 RTC,再发 sync start
  启动初始对时(`Sync[InitTrain] ... n=N` 是设备自动跑的对时交换),之后进入 `Sync[Live]`
  周期对时。**RTC 只在这个阶段被重写** —— 所以要每天 reset 重连一次来重新锚定时钟。
- `Cmd:` 是设备→console 的协议消息累计数(状态心跳约 1 条/秒 + 对时响应 + 操作 ack)。
  等它涨到 ~256 只是"连接已稳定、初始化已完成"的经验判据,不是某条指令。
- `Sync[Live] dev=... err=... dly=...`:dev = 设备钟与主机钟的偏差;err = 每次对时的
  测量误差(超过阈值显示 `outlier` 并被剔除,不参与统计);dly = BLE 往返延迟。
- Record Start 实际只发一条 3 字节 `record start` 命令然后等 ack;ack 走丢就会留下
  `record start failed:` 的残留状态,但命令本身往往已生效 —— 以 Recording time / Storage
  为准。
