# 交付目录 v0.3.4

本目录是 2026-11-16 交付包中**可以进 Git 的部分**。完整交付包共 7 个文件、合计 1.82 GB，其中模型包体积过大，按仓库既有约定不入库（见下文「模型包」）。

## 目录内容

| 文件 | 大小 | 说明 |
|---|---|---|
| `InterviewFeedback-0.3.4-bc10024-debug.apk` | 30,515,604 B | 装机包，`SOURCE_REVISION=bc10024…`，能通过 FORMAL 模式校验 |
| `S1_真机验收记录_20261114.md` | 110,182 B | 总验收记录，§5 已并入手机侧 S3 数据 |
| `S2_质量评测报告_20261115.md` | 16,384 B | 30 段数据集质量评测 |
| `S3_三模式对照报告_20261115.md` | 23,316 B | 三模式对照，桌面侧 §3 与手机侧 §3.3 |
| `交付说明.md` | — | 装机、运行、验收状态、已知限制 |
| `SHA256SUMS.txt` | — | 本目录内四个文件的校验和 |
| `README.md` | — | 本文件 |

## 模型包

`android-models-rulesv2.zip` 为 1,792,940,504 B（1.79 GB），SHA-256 `78FF83B24AEF8D05BE0E7C86FEE609FD60A5FEA33DCB77949CF70A76795DBB3F`。

**它不在仓库里**，原因有两条：

1. 超过 GitHub 单文件 100 MiB 硬限，Git LFS 免费额度（1 GB 存储 + 1 GB/月带宽）也承载不了这个体积；
2. 仓库既有约定本来就不存权重——`models/README.md` 明确写了「不上传权重或包含它们的模型 ZIP」。

### 直接下载（推荐）

模型包作为 Release 资产托管，clone 仓库不会被拉取，需要时单独下载：

<https://github.com/Fionaxxxi/SA-lab/releases/download/v0.3.4/android-models-rulesv2.zip>

同一个 Release 也附带本目录的 APK。下载后核对哈希：

```powershell
Get-FileHash -LiteralPath .\android-models-rulesv2.zip -Algorithm SHA256
# 应为 78FF83B24AEF8D05BE0E7C86FEE609FD60A5FEA33DCB77949CF70A76795DBB3F
```

上传完成后已比对 GitHub 侧 `sha256:` digest，与本地逐位一致；大小 1,792,940,504 B 也一致。

### 自己重新生成

前提：已有原始权重放在 `models/weights/`。

```powershell
python models/package_models.py --verify-only                                  # 逐项核对清单 SHA256
python models/package_models.py --output models/android-models.zip             # 生成手机包
```

`--verify-only` 会按 `models/manifest.json` 逐项校验；清单与文件不符时打包程序会拒绝打包。若需从零下载权重，先执行 `python models/prepare_models.py --semantic-revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42 --silero-revision 066409f3d9db45a30d21dfcbf9147826ffdd7052`。

> 重新打出来的 ZIP 与原交付包那份**字节不一定相同**（ZIP 内含时间戳）。手机正式运行配置绑定的是**实际导入**的 ZIP 清单字节，所以重打之后要重新走一遍导入与 `model_version` 核对。

### 从原交付包取

原始文件在交付机 `D:\Computation_Partitioning\交付包_20261116\android-models-rulesv2.zip`；手机上可能还留有推送过的副本（`/sdcard/android-models-rulesv2.zip`）。

## 两个 APK 不要混用

| 文件 | 能否跑 FORMAL | 原因 |
|---|---|---|
| 本目录 `…-bc10024-debug.apk` | 能 | `SOURCE_REVISION` 是完整 40 位哈希 |
| 原交付包 `InterviewFeedback-0.3.4-debug.apk` | 不能 | `SOURCE_REVISION = UNVERSIONED`，被 `apkCommit.matches("[0-9a-f]{40,64}")` 拒绝 |

## 原始证据在哪

手机侧证据不在本目录，在：

- `experiments/results/s3_phone_20261116/` — 4 份 task、3 份 run-record、6 张截图、README（FORMAL，S01 四要点）
- `experiments/results/s1_034_phone_20261115/` — 7 张截图、README（`0.3.4` 复跑，MANUAL，手填三条要点）
- `experiments/configs/run-S01-{LOCAL,REMOTE,MIXED}.json` — 三份运行配置
- `experiments/samples/manifest.json` — 30 条样本清单

上述文件均声明了 `-text`（截图除外，PNG 按二进制），按原字节入库。clone 后可用 `sha256sum` 或 `Get-FileHash` 逐条核对 README 中列出的哈希。
