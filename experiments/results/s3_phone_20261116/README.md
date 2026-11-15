# S3 手机侧三模式对照记录（2026-11-16）

## 1. 记录性质

单台真机在同一份**已登记样本** S01 上，以 `FORMAL` 条件依次跑通 `LOCAL` / `REMOTE` / `MANUAL_MIXED` 三种执行模式，由 App 导出任务记录与运行记录，并保留人工截图。

**这是正式实验记录，不是冒烟测试**，判据如下：

- `condition = FORMAL`，三份运行记录的 `run_id` 互异且与 `experiments/configs/run-S01-{LOCAL,REMOTE,MIXED}.json` 一一对应；
- `sample_id = S01` 已在 `experiments/samples/manifest.json` 登记，且 `sample_sha256 = actual_wav_sha256 = c20bef21…fb14`；
- 任务记录含 `experiment` 段（条件、配置哈希、样本清单哈希、样本哈希、题号、分片）。

本目录只保留任务记录、运行记录与人工截图；**不含音频原始文件与 WAV 原件**（样本在 `experiments/samples/local/`）。

## 2. 采集条件

| 项 | 值 |
|---|---|
| 设备标识 | `android-d6b42be2-c262-40c0-a382-0b72ccf4f8d2` |
| 机型 / 系统 | `ELI-AN00` / Android 16（sdk 36）/ `arm64-v8a` |
| APK | `0.3.4`（versionCode 8） |
| APK 来源提交 | `bc1002476144d75932d7936bf0fa106ff1f0d3de` |
| 构建方式 | `gradle assembleDebug -PsourceRevision=bc10024…`，把完整 40 位哈希注入 `BuildConfig.SOURCE_REVISION`；缺这一步 FORMAL 条件校验不过 |
| 模型 | `modelset-e8f8c211226b-066409f3d9db-9ba59cbaae79` |
| 配置 | `rules-v2` |
| 样本清单摘要 | `e4f9ce67f202f6d2b33ad293acc9280cb9fec0cd230aa40488193944cabd39ae` |
| 样本 | `S01`，`topic_id = T01`，`split = calibration`，`sha256 = c20bef21a864bb559bb8b8c12a3691c7d7828e03f9feff5807f14d45c310fb14` |
| 输入 | `IMPORT`（经 SAF 导入 `/sdcard/Download/S01.wav`，583,076 B，4 条要点） |
| 音频长度 | `audio_samples = 291,499` → 18.2187 s |
| 网络 | `WIFI`，网关与手机同局域网，端口 8000 |
| 电源 | 充电中，电量 99% |
| 预热 / 缓存 | `COLD` / `DISABLED` |
| 温度 | **未记录**（run 配置 `temperature_c = null`） |
| 服务端提交 | **未记录**（run 配置 `service_commit = null`） |

三种模式唯一的人工变量是 `assignments`，M0（采集）与 M5（反馈）固定本地：

| 模式 | M1 | M2 | M3 | M4 |
|---|---|---|---|---|
| `LOCAL` | 本地 | 本地 | 本地 | 本地 |
| `REMOTE` | 远程 | 远程 | 远程 | 远程 |
| `MANUAL_MIXED` | 本地 | 远程 | 远程 | 本地 |

## 3. 任务清单

四条任务，全部 `SUCCEEDED`、`effective_input = true`、覆盖 4/4、无 `error_code`：

| run_id | task_id | 到结果 / 到反馈 (ms) | 上传 / 下载 (B) |
|---|---|---|---|
| `s3phone-S01-LOCAL` | `e549a0ad-27bc-4e1e-a58d-c95d84dfa5c5` | 32,224 / 32,395 | 0 / 0 |
| `s3phone-S01-REMOTE` | `9527b17b-c546-43b5-9b57-a2e36e8c61f2` | 6,109 / 6,197 | 1,703,128 / 795,640 |
| `s3phone-S01-MIXED` | `da8343ba-9310-4a7c-a43c-530c110234c9` | 5,070 / 5,114 | 778,314 / 82,580 |
| `s3phone-S01-MIXED`（同条件第二次） | `8aa3dec0-6b34-4ec3-bc76-34e00d3327ae` | 10,084 / 10,143 | 778,314 / 82,580 |

逐模块 `elapsed_ms`：

| 模块 | LOCAL | REMOTE | MIXED | MIXED(2) |
|---|---|---|---|---|
| M0 | 74 | 73 | 98 | 101 |
| M1 | 590 | 93 | 449 | 498 |
| M2 | 24,012 | 4,328 | 3,750 | 4,061 |
| M3 | 2,748 | 139 | 46 | 78 |
| M4 | 26 | 0 | 11 | 21 |
| M5 | 3 | 3 | 2 | 2 |

四条要点分值（`feedback.matches[*].score`，全精度）：

| 要点 | LOCAL | REMOTE | MIXED | MIXED(2) |
|---|---|---|---|---|
| k1 | 0.7126780431504034 | 0.7126781685820430 | 同 REMOTE | 同 REMOTE |
| k2 | 0.5826187834028684 | 0.5826187369460704 | 同 REMOTE | 同 REMOTE |
| k3 | 0.8035757270650615 | 0.8035757863093425 | 同 REMOTE | 同 REMOTE |
| k4 | 0.5852711363191931 | 0.5852711569953376 | 同 REMOTE | 同 REMOTE |

REMOTE 逐模块流量（B）：

| 模块 | up | down | 往返 ms |
|---|---|---|---|
| M1 | 843,140 | 712,088 | 682 |
| M2 | 777,241 | 819 | 4,740 |
| M3 | 1,073 | 81,762 | 202 |
| M4 | 81,674 | 971 | 96 |

MIXED 逐模块流量（B）：M2 up 777,241 / down 819（往返 4,244 ms）；M3 up 1,073 / down 81,761（往返 122 ms）；M1 与 M4 为本地，无网络字节。

## 4. 可支撑的结论

1. **三模式在手机侧均端到端跑通**：四条任务全部 `SUCCEEDED`，覆盖 4/4。
2. **样本身份无歧义**：四条任务的 `sample_sha256` 与 `actual_wav_sha256` 均为 `c20bef21…fb14`，与 `manifest.json` 登记的 S01 一致。即 App 实际送去分析的就是登记样本，没有退回界面手填要点。
3. **执行位置与计划一致**：LOCAL 六模块全 `LOCAL` 且 `bytes_up/down` 全为 0；REMOTE 中 M1–M4 全 `REMOTE`；MIXED 中仅 M2/M3 为 `REMOTE`、M1/M4 为 `LOCAL`。
4. **REMOTE 与 MIXED 结果同源**：两种模式的四条分值逐位相同，覆盖一致。
5. **同一输入下链路是确定性的**：`da8343ba` 与 `8aa3dec0` 在同一 `run_id`、同设备、同条件下重跑，四条分值仍逐位相同。
6. **混合模式换来上传流量下降**：REMOTE 上传 1,703,128 B，MIXED 上传 778,314 B，单样本口径降幅 54.3%。

## 5. 不可支撑的结论

| 缺口 | 依据 | 说明 |
|---|---|---|
| 不能主张与桌面逐位一致 | 桌面基准只存 6 位小数 | 见 §6.2，2.729e-7 的差值主要来自基准舍入 |
| 不能声称性能达标 | LOCAL 32.2 s、M2 24.0 s | 端侧算力差异，未与设计目标对照 |
| 不能归因 PCM 字节偏差 | 手机 M1/M2 上传各比桌面多约 65 KB | 见 §6.3，成因未查 |
| 不能归因重复跑的 5,014 ms 差 | `8aa3dec0` 慢于 `da8343ba` | 见 §6.4，约 4.6 s 无模块级归属 |
| 不是两机验收 | 单一设备 | `docs/team-s0-s3.md` 要求两台手机验证并签收 |
| 不能排除热节流 | `temperature_c = null` | 温度未记录 |
| 不能排除服务端版本漂移 | `service_commit = null` | 网关提交未记录 |
| 只有 S01 | 单样本 | 不代表 30 段整体 |

## 6. 性能观察

### 6.1 端侧算力是 LOCAL 的瓶颈

LOCAL 32,224 ms 里 M2 占 24,012 ms（74.5%）、M3 占 2,748 ms（8.5%）。桌面同链路 M2 为 3,797 ms、wall 3,936 ms；手机 LOCAL 是桌面 LOCAL 的 8.19 倍（32,224 / 3,936）。

把 M2 挪到电脑后（REMOTE），wall 降到 6,109 ms，为 LOCAL 的 19.0%。

### 6.2 与桌面基准的差异

桌面基准 `three-modes-S01.json` 只存 6 位小数，手机为全精度。逐项绝对差：

| 要点 | LOCAL | REMOTE / MIXED |
|---|---|---|
| k1 | 4.315e-8 | 1.686e-7 |
| k2 | 2.166e-7 | 2.631e-7 |
| k3 | 2.729e-7 | 2.137e-7 |
| k4 | 1.363e-7 | 1.570e-7 |

最大 2.729e-7，小于桌面基准 6 位小数的半个末位（5e-7）。因此该差值落在基准精度内，**不能作为链路偏差的证据**。

另有一个可确认的真实观察：同一台手机上 LOCAL 与 REMOTE/MIXED 的分值并不完全相同（k1 差 1.254e-7、k2 差 4.646e-8、k3 差 5.924e-8、k4 差 2.068e-8），说明端侧与远端在浮点运算路径上有微小差别。该差别远小于阈值判定余量——离 0.54 最近的 k2 为 0.5826，余量 0.0426——不影响覆盖判定。

### 6.3 上传字节偏差（待查）

| 模块 up | 手机 REMOTE | 桌面 REMOTE | 差 |
|---|---|---|---|
| M1 | 843,140 | 777,683 | +65,457 |
| M2 | 777,241 | 712,047 | +65,194 |
| M3 | 1,073 | 1,052 | +21 |
| M4 | 81,674 | 81,720 | −46 |

MIXED 下 M2 up 777,241 对 712,059（+65,182）、M3 up 1,073 对 1,064（+9）。

M1 与 M2 各多约 65 KB，且 M2 上传的正是 M1 输出的 PCM，两者偏差量接近，指向同一处差异；M3/M4 的载荷偏差都在 ±50 B 内，说明不是整体序列化格式变化。**成因未定位**，记为待查项。

### 6.4 重复跑的 5,014 ms 差

`8aa3dec0` 比 `da8343ba` 慢 5,014 ms（10,084 对 5,070）。逐项看：M2 往返差 337 ms（4,581 对 4,244）、M3 往返差 10 ms、M0/M1/M4/M5 节点耗时差合计 62 ms。可归属部分合计 409 ms，**剩余约 4.6 s 无模块级归属**，未作定论。

## 7. 后续动作（建议）

1. 查清 §6.3 的 65 KB 上传偏差。若确认为手机侧多传冗余载荷，REMOTE 的流量收益会被低估约 4 个百分点（按少传 130,651 B 重算，降幅为 50.5% 而非 54.3%）。
2. 给 run 配置补 `temperature_c` 与 `service_commit`，否则无法排除热节流与服务端版本漂移。
3. 补第二台手机做两机验收。
4. 把 S02、S05 的手机侧也跑一遍，把单样本结论扩到三样本。
5. 若 §6.4 的 4.6 s 差能复现，需要更细的时间戳；当前只有模块级 elapsed，无法拆到等待段落。

## 8. 文件清单

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `task-LOCAL.json` | 3,556 | `be9f452f22575349c88cd641d8014cb71e3322e655a27e42bca7abbfe2980856` |
| `task-REMOTE.json` | 3,566 | `f4d6121e2084383affb8bea8578e7867cf9b9213b67d20df3638cd069a73efaa` |
| `task-MIXED.json` | 3,564 | `b9b073f08d6ba553ba47202a9a7794c15d674fd9d948048072ee0fc396ab86d5` |
| `task-extra-8aa3dec0.json` | 3,567 | `9c3f7d2238959a1959722b22ac045ea8cb4d511764aaca3e78077c84d9b55cdf` |
| `run-record-LOCAL.json` | 564 | `1d0b675cab638e76bbfb5ebb5d082fc6bcd486333243961dd28408bf18343b40` |
| `run-record-REMOTE.json` | 570 | `8292549deb76906c9765995df1f5aaf27d24b1f9c6b2a8032bb658aaa627c9b2` |
| `run-record-MIXED.json` | 573 | `19c0be8a63145e18e9d8849c67f2d9768d9007ba4e29c19c4f41724599dda23c` |
| `S01-LOCAL-result.jpg` | 816,093 | `bbece33c1cbe5f6b80f758ab01436c44216a848a0d33114f973bfdef72293a32` |
| `S01-LOCAL-evidence.jpg` | 679,117 | `1aa86928d7f297a8de15b14876eb413141d3d5ae9179734940f5a30ee9bf73bd` |
| `S01-REMOTE-result.jpg` | 1,006,010 | `1dc5ea057c04502d3ae5b2a233cda3c11a366d18dd3ab43b194a84a7425ea1dd` |
| `S01-REMOTE-evidence.jpg` | 855,963 | `6a00c10e8e492d6ff7c4eadac3db8881b27060a3f38babd5aaea2267bf493d2a` |
| `S01-MIXED-result.jpg` | 1,020,766 | `0d4767e640bafe826fb2876af328c8f9f0069423ce78e4d2115cd026fab07f2e` |
| `S01-MIXED-evidence.jpg` | 797,343 | `94176aeec3ba333a254a26f21ad87528fc11d7af69f9f7ba3eaef6ec671be3be` |

配套的三份运行配置存放在 `experiments/configs/`：

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `run-S01-LOCAL.json` | 1,182 | `e9456aa651e8beb219c22b38f299d9aba8bfb4bcbc6ec30a896356d1633ad17e` |
| `run-S01-REMOTE.json` | 1,184 | `9ea440b35a44777b5bc6f44c0ed81c07b0dbb7fde19dbf19d70c587f3a20342b` |
| `run-S01-MIXED.json` | 1,243 | `a07f85c9087f0845ea3d2c42baf5953229c686339afae68c28a80b47074f5554` |

三份 `run-record` 的 `run_config_sha256` 与上表逐个相等；`sample_manifest_sha256` 均为 `e4f9ce67…39ae`，等于仓库内 `experiments/samples/manifest.json` 的哈希（该文件同样声明了 `-text`）。哈希链闭合，clone 之后可直接用 `Get-FileHash` 或 `sha256sum` 逐条复验。

> 这三份配置与 `manifest.json` 原本受 `*.json text eol=lf` 约束，入库时会被去掉行尾字节，导致仓库内的哈希与记录值不符。本目录与这三份配置、以及 `manifest.json` 都声明了 `-text`，Git 不再做行尾规范化，仓库内容与导出原件逐字节相同。
>
> 核对时请以 `9d974f5` 及之后的提交为准。`0b7e55e` 到 `e7445ad` 之间的提交里，`manifest.json` 仍是 LF 版，SHA-256 为 `87ddd1055c824bd9ed2f592c8dbcb83dafdebadb4d1daddbaa92f4ff3c226e96`，与这里的 `e4f9ce67…` 不符——那正是本次修复的目标。

`task-*.json` 是 App 导出的原始文件，**保留 UTF-8 BOM 与 CRLF**。读取请用 `utf-8-sig`，否则 Python 的 `json.load` 会抛 `Unexpected UTF-8 BOM`。

本目录与三份 `run-S01-*.json` 已在仓库 `.gitattributes` 中声明 `-text`，Git 不做行尾规范化，入库内容与导出原件逐字节一致，上表哈希可直接用 `Get-FileHash` 或 `sha256sum` 核对。若没有这条声明，`*.json text eol=lf` 会去掉末尾换行，哈希将全部改变。

截图取自同一台设备；`*-result.jpg` 记录要点覆盖与分值，`*-evidence.jpg` 记录运行条件（`run_id`、样本清单条数、输入方式）、任务号与逐模块执行位置与耗时。REMOTE/MIXED 截图中凭据框为圆点遮罩，明文不可见；服务地址为局域网内网地址，已在验收报告 §2 与 §5.2 公开。

## 9. 复算方法

```
音频秒数   = audio_samples / 16000          （S01: 291,499 / 16,000 = 18.2187 s）
单模块流量 = bytes_up / bytes_down           （LOCAL 恒为 0）
上传合计   = Σ bytes_up
上传降幅   = 1 - MIXED_up / REMOTE_up        （1 - 778,314 / 1,703,128 = 54.3%）
跨端差值   = |手机 score（全精度） - 桌面 score（仅 6 位）|
重复性判据 = 两份 task 的 feedback.matches[*].score 逐位相等
```

`audio_samples` 在 `TASK_TERMINAL` 与各 `MODULE_END` 中一致，可直接取任务记录里的 `audio_samples`。
