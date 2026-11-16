# S1 手机侧 0.3.4 复跑记录（2026-11-15）

## 1. 记录性质

单台真机在 `0.3.4`（versionCode 8）上复跑 S1 的手机侧链路：导入 WAV 分析、权限拒绝与授予、录音态、纯静音。共 7 张人工截图，覆盖一次完整成功路径与两条失败分支。

**这是 S1 链路验证记录，不是 FORMAL 实验记录。** 区别必须写明：

- 本次走的是**界面手填要点 + `unregistered` 样本**路径，没有注入运行配置与样本清单，因此任务记录里 `condition` 不是 `FORMAL`，`sample_id` 是 `unregistered-d84ca057-2426-4d6f-97da-b3aeed91694c` 而非 S01；
- 手填要点为界面默认三条（调查居民需求 / 组织分层宣传 / 评估宣传效果），因此覆盖判定是 3/3，不是 4/4；
- 正式的 FORMAL 四要点 S01 记录在 `experiments/results/s3_phone_20261116/`，两者不可互相替代。

本目录只保留截图，**不含任务 JSON 与运行记录**（本次未导出）。截图中的任务编号与耗时可直接作为设备端读数引用。

## 2. 采集条件

| 项 | 值 |
|---|---|
| 设备机型 / 系统 | `ELI-AN00` / Android 16（sdk 36）/ `arm64-v8a` |
| 设备序列号 | `AQULVB4522044827` |
| APK | `0.3.4`（versionCode 8） |
| APK 版本证明 | `S1-034-import-detail.png` 页脚显示 `语音回答反馈 · v0.3.4` |
| 模型 | 模型清单已安装（`S1-034-home.png` 状态条「就绪 · 模型清单已安装」） |
| 运行模式 | `MANUAL`（任务运行编号前缀 `manual-`） |
| 输入 | `IMPORT`，经 SAF 选择 `/sdcard/Download/S01.wav` |
| 要点 | 界面手填 3 条（非登记样本的 4 条） |
| 采集日期 | 2026-11-15，15:26–15:59 |

## 3. 场景清单

| # | 场景 | 截图 | 设备端读数 |
|---|---|---|---|
| 1 | 装机后首页就绪 | `S1-034-home.png` | 状态条「就绪 · 模型清单已安装」，15:26 |
| 2 | 权限拒绝后的提示 | `S1-034-perm-denied.png` | 状态条「未获得录音权限：可在系统设置中开启，或改用「导入 WAV 并分析」」，15:27 |
| 3 | 权限授予后的提示 | `S1-034-perm-granted.png` | 状态条「已获得录音权限，请再次点击「录音／停止并分析」开始」，15:27 |
| 4 | 录音进行中 | `S1-034-recording.png` | 状态条「正在录音 · 再次点击停止并分析」；按钮转为「停止录音并分析」，计时 `00:02`，15:28 |
| 5 | 纯静音 | `S1-034-nospeech.png` | 状态条「分析失败 · NO_SPEECH」，15:28 |
| 6 | 导入 WAV 分析结果 | `S1-034-import-result.png` | 要点覆盖 **3/3**，完整反馈 **17.94 秒**，相似度 0.845 / 1.000 / 0.768，15:58 |
| 7 | 节点耗时与任务详情 | `S1-034-import-detail.png` | 见下表，15:59 |

## 4. 任务详情（第 7 张截图逐项）

| 字段 | 值 |
|---|---|
| 任务编号 | `59c30577-f10d-46f8-9772-542ad5a14ee2` |
| 运行编号 | `manual-e131078c-2063-45c1-821f-8c5dd75368bc` |
| 样本 | `unregistered-d84ca057-2426-4d6f-97da-b3aeed91694c` · 未分类 |
| 状态 | `SUCCEEDED` |
| 到结果保存 | 17,849 ms |
| 到完整反馈 | **17,940 ms** |

逐节点耗时与执行位置：

| 节点 | 位置 | 状态 | 耗时 |
|---|---|---|---|
| M0 | 手机本地 | OK | 66 ms |
| M1 | 手机本地 | OK | 622 ms |
| M2 | 手机本地 | OK | 14,117 ms |
| M3 | 手机本地 | OK | 2,854 ms |
| M4 | 手机本地 | OK | 25 ms |
| M5 | 手机本地 | OK | 7 ms |

六节点全部本地，与 `MANUAL` 模式的归属一致。M2（ASR）占 14,117 ms，是端到端耗时的主要构成。

## 5. 文件清单与哈希

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `S1-034-home.png` | 245,074 | `F7988CBDE79BDC9090FE93C666F0607D145459A0D9F690E0A57BE04268FC53EA` |
| `S1-034-import-detail.png` | 325,946 | `DCD2CFED02D294FB6ADEB91FBED787E1998A9079080A1D3B76A97666C7FB11D9` |
| `S1-034-import-result.png` | 377,813 | `1C1B04D058971DD0A4554783BAED2901BFD6F85F343EC1127B16418FA5095CFE` |
| `S1-034-nospeech.png` | 244,887 | `834DE41394667C64D3A9E8FC901162CADC3BCB8828032B9328EA1BB829B575D6` |
| `S1-034-perm-denied.png` | 263,282 | `2250209BE4DB654EB2F8FB79524F0D57139B654FBFE37569D5F729080CBD2088` |
| `S1-034-perm-granted.png` | 253,004 | `418231CCD7E83A1AD616B0CF3B7807A3E882705DFD6F1CC538A1012F3C80641F` |
| `S1-034-recording.png` | 238,851 | `4D58EE81A3D1DADD6B108532BC25F693E56E49F02863BB0F3005DA80C9BF4C57` |

合计 7 个文件、1,948,857 B。

PNG 为二进制文件，`.gitattributes` 的 `* text=auto` 会自动按二进制处理，不受行尾规范化影响，clone 后哈希应与上表一致。

## 6. 复现

```powershell
# 1) 装带版本号的 APK（本例 APK 同时作为交付物在 deliverables/v0.3.4/）
adb install -r .\deliverables\v0.3.4\InterviewFeedback-0.3.4-bc10024-debug.apk

# 2) 导入模型包（约 1.79 GB，见 deliverables/v0.3.4/README.md 的获取方式）
adb push .\android-models-rulesv2.zip /sdcard/

# 3) 在 App 内：模型管理 → 选择 ZIP → 等待解压完成
# 4) 选「选择 WAV 文件分析」→ 从 Download 选 S01.wav
# 5) 展开「节点耗时与任务详情」读取 task_id 与逐节点耗时
```

权限分支：

```powershell
# 清掉授权记录后再进 App，可复现「未获得录音权限」提示
adb shell pm clear-permission-flags com.example.interviewfeedback android.permission.RECORD_AUDIO user-set user-fixed
```

## 7. 已知限制

| 项 | 说明 |
|---|---|
| 非 FORMAL | 手填要点 + `unregistered` 样本，无 run 配置注入，任务记录 `condition` 非 `FORMAL` |
| 覆盖是 3/3 不是 4/4 | 界面默认三条要点，与登记样本 S01 的 4 条不同 |
| 单机 | 仅 `AQULVB4522044827`，无第二台设备 |
| 无任务 JSON | 本次未导出 `task.json` / `run-record`，只有截图；需要机器可校验的记录请用 `s3_phone_20261116/` |
| 无温度与服务端提交 | 本次未记录 `temperature_c` 与 `service_commit` |
| 要点来源 | 手填要点未留档，仅截图可见；判定走了 `MainActivity.kt:288` 的 `manualPoints` 分支 |

## 8. 与 S1 验收条目的对应

| 条目 | 本记录能证明 | 仍缺 |
|---|---|---|
| S1-T1 离线正常路径 | 导入 WAV 成功 3/3、17.94 s，六节点全本地 | 真人录音成功路径的同一批截图；第二台设备 |
| S1-T2 权限/静音/缺模型 | 权限拒绝与授予的提示文案正确；纯静音返回 `NO_SPEECH` | 缺模型 ENOENT 分支的截图；坏 WAV 拒绝的截图；第二台设备 |
| S1-T3 连续/取消/重启 | — | 本批截图未覆盖，见 `D:\Computation_Partitioning\` 的 `b106_*` 系列 |

## 9. 变更历史

| 日期 | 变更 |
|---|---|
| 2026-11-15 | 采集 7 张截图 |
| 2026-11-16 | 从 `D:\Computation_Partitioning\v034_*.png` 归档入库，目录按实际拍摄日期命名 |
