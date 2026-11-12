# S1 真机手动冒烟记录（2026-11-12）

## 1. 记录性质

组员在真机上执行的 3 次手动任务的事件流导出，用于佐证 Android 端 M0–M5 可以贯通。

**这不是正式实验。** 三次任务的 `plan_version` 均为 `manual-LOCAL`，`sample_id` 均为 `unregistered-<uuid>`，`experiment` 均为 `null`。样本未登记、没有实验编号、事件里没有时间戳。因此：

- 它不作为 S2 基线数据；
- 它不作为 S1 出口验收依据（S1 出口还要求第二台设备与签收）；
- 它只回答一个问题：链路通不通。

## 2. 采集条件

数据来自同一次导出的 `device-info.json` 与两份事件流。

| 项 | 值 |
|---|---|
| 设备标识 | `android-564b48fb-7328-4b28-ab4e-c2fc23e337fe` |
| 型号代码 | `23127PN0CC`（市场机型名未核实） |
| 系统 | Android 15，ABI `arm64-v8a` |
| 电源 | `POWER_SAVE`，未充电，电量 72%，温度 33.4 °C |
| APK | `0.2.0`，commit `3ae57e954bd37c1c4fdc1e86a87f08dcaee279ae` |
| 模型集 | `modelset-e8f8c211226b-066409f3d9db-9ba59cbaae79` |
| 配置 | `rules-v1` |
| manifest 摘要 | `3c908bb523a80c30b2648cb9b08b4869d6b300ae54f3437455e1a8bb0f13fcf0` |
| 执行模式 | `LOCAL`，全本地 |
| 网络传输 | `bytes_up = 0`，`bytes_down = 0` |

## 3. 任务清单

音频时长按 `audio_samples / 16000` 换算（16 kHz 单声道）。

| task_id | 音频 | M0 | M1 | M2 | M3 | M4 | M5 | 整链 | 结果 |
|---|---|---|---|---|---|---|---|---|---|
| `75f4f228-78d6-403f-8f2d-619b77de1123` | 0.896 s | 78 ms | 144 ms | — | — | — | — | 3,799 ms | `FAILED` / `NO_SPEECH` |
| `044b5060-8bfd-4585-9d98-a89bf0090457` | 17.024 s | 106 ms | 200 ms | 19,887 ms | 2,093 ms | 9 ms | 2 ms | 22,321 ms | `SUCCEEDED` |
| `cc703b8a-7fd1-4d93-9f6a-125e043e91c2` | 10.112 s | 181 ms | 308 ms | 16,691 ms | 1,848 ms | 8 ms | 2 ms | 22,849 ms | `SUCCEEDED` |

`events-2tasks.jsonl` 是前两次任务的导出（13 行），`events-3tasks.jsonl` 是全部三次的导出（22 行）。前者的 13 行与后者的前 13 行逐字相同。

## 4. 可支撑的结论

1. M0–M5 六段在真机上全部执行，2 次任务以 `TASK_TERMINAL / SUCCEEDED` 结束，`FEEDBACK_VISIBLE` 在终态后 78 ms 触发（22,399 与 22,321）。
2. 失败路径正确：0.896 s 音频在 M1 被判 `NO_SPEECH`（144 ms），任务于 3,799 ms 终止，未继续执行后续模块。
3. `LOCAL` 模式确实未走网络：两次成功任务的上下行字节均为 0。
4. `model_version`、`config_version` 与仓库 `models/manifest.json` 一致。

## 5. 不可支撑的结论

| 缺口 | 依据 | 说明 |
|---|---|---|
| 不代表当前 `main` | `apk_commit = 3ae57e9` | 该提交在 `main` 的 14 个提交中排第 5，其后还有 9 个提交；当前 `mobile/app/build.gradle.kts` 为 `versionName "0.3.0"` / `versionCode 4`，与实测 APK 的 `0.2.0` 不同 |
| 不是正式实验 | `sample_id` 为 `unregistered-*`，`experiment = null` | 不可作为 S2 基线，也不计入“30 段标注” |
| 无法复算吞吐与时序 | 事件字段无 `ts` / `occurred_at` | 只能按 `elapsed_ms` 看单次任务内部耗时，不能还原任务到达间隔 |
| 未满足 S1 出口 | 单一设备 | `docs/team-s0-s3.md` 要求两台手机验证并签收 |

## 6. 性能观察

### 6.1 M2 是本链瓶颈

`044b5060` 中 M2 占整链 **89.1%**（19,887 / 22,321）。

整链 22,321 ms 与 22,849 ms，相对设计中“端到端 P90 ≤ 5 s”的目标分别高出 **4.46 倍**与 **4.57 倍**。该目标在 `docs/quality-report.md` 中标注为设计目标、未实测，此处是首次真机实测值，但受“旧 APK + 省电模式”两个条件影响，不能直接当作最终性能结论。

### 6.2 M2 含约 12 秒固定开销

两条成功记录反解：

```
19.887 = a + b × 17.024
16.691 = a + b × 10.112
```

解得 `b ≈ 0.46`、`a ≈ 12.0 s`。即每次 M2 约先付 12 秒固定成本，再按 0.46 倍音频时长增长。这解释了为什么 10.1 s 音频的 RTF 为 1.65、17.0 s 音频反而降到 1.17。

代码侧可对照 `mobile/app/src/main/java/com/example/interviewfeedback/analysis/semantic/RealModules.kt`：

- 第 28 行 `private val asrResource = lazy { Model(...) }`，`Model` 只加载一次并被缓存；
- 第 111 行 `Recognizer(asrModel, 16000f).use { ... }`，`Recognizer` 每个任务新建一次。

**推断**：固定开销来自 `Recognizer` 构造（解码器初始化、rescorer 挂载，`models/weights/vosk-model-cn-0.22/graph/HCLG.fst` 559 MB、`rescore/G.carpa` 1,197 MB）。**这是推断，未在本机验证**——本机缺少 NDK 与 CMake，无法构建该 APK，也没有在该 APK 内加耗时埋点。

### 6.3 模块耗时之和与总时长对不上

- `044b5060`：模块耗时之和 22,297 ms，`TASK_TERMINAL` 22,321 ms，差 24 ms。
- `cc703b8a`：模块耗时之和 19,038 ms，`TASK_TERMINAL` 22,849 ms，差 **3,811 ms（16.7%）**。

第二处差额说明任务中存在未被模块计时覆盖的等待。若后续报告要写“节点耗时可加和等于总时长”，当前数据不足以支撑。

### 6.4 可能的放大因素

`device-info.json` 记录 `power_mode = POWER_SAVE`、`charging = false`。省电模式会限制 CPU 调度，可能放大固定开销。目前只有一份设备信息，无法确认三次任务是否都在该模式下执行，也没有性能模式对照组。

## 7. 后续动作（建议）

1. 在性能模式下用同一 APK 重测一次，分离“代码开销”与“调度降频”。
2. 试 `Recognizer` 复用（`reset()` 或实例池），把 12 秒固定成本摊掉；这一步收益最大、改动最小。
3. 以上两步无改善后，再评估换轻量模型或换引擎——换模型会使已采标注作废，必须放在最后。

## 8. 文件清单

| 文件 | 原始文件名 | 字节 | SHA-256 |
|---|---|---|---|
| `device-info.json` | `device-info.json` | 621 | `5e45e3a927b922753584c8025a3d85d96aa708f157d5193ca86c373e7b2b1959` |
| `events-2tasks.jsonl` | `events.jsonl.json` | 9,375 | `b3ff4c452ad2f7559c4c779a1b38596ea196acf25d417d070c0061de50644123` |
| `events-3tasks.jsonl` | `events.jsonl (1).json` | 15,855 | `2b4df25c0c80276d98eb2e92055febb1a99dd43639cf8e9ae7e05510d9fb8787` |

原始文件由组员通过微信发送，未包含音频与转写文本；本目录只保留脱敏元数据。

同批发送的 `houji-ota_full-OS2.0.104.0.VNCCNXM-user-15.0-9300a7608a.zip.cfg` 是手机系统 OTA 包的二进制配置，与本项目无关，未归档。

## 9. 复算方法

```
音频秒数 = audio_samples / 16000
模块占比 = 模块 elapsed_ms / TASK_TERMINAL elapsed_ms
M2 线性反解：用两条成功任务的 (音频秒数, M2 elapsed_ms) 解二元一次方程
```

`audio_samples` 取 `TASK_TERMINAL` 事件中的值（与各 `MODULE_END` 一致）。
