# JVM 单元测试基线（2026-11-13）

## 目的

把 `:app:testDebugUnitTest` 从「执行 0 个用例」变成「有真实用例、有真实通过数」，同时补上仓库缺失的 Python 依赖声明。这是 S1/S2 测试岗的第一份可复现交付物，不替代任何真机验收。

## 环境（本机实测）

| 项 | 值 |
| --- | --- |
| JDK | `D:\Java\jdk-17.0.21+9`（17.0.21） |
| Gradle | `D:\gradle-8.2`（8.2） |
| Android SDK | `D:\Android\Sdk`（compileSdk 34） |
| NDK | `26.1.10909125` |
| CMake | `3.22.1` |
| Python | `D:\Python311\python.exe`（3.11.9），venv 位于 `D:\Computation_Partitioning\SA-lab\.venv` |
| 代理 | `127.0.0.1:7897`（GitHub 访问需要；`dl.google.com`/`repo.maven.apache.org` 直连可用） |

## 本次改动

| 文件 | 变更 |
| --- | --- |
| `mobile/app/build.gradle.kts` | 新增 `testImplementation("junit:junit:4.13.2")`、`testImplementation("org.json:json:20240303")`、`androidTestImplementation("androidx.test.ext:junit:1.1.5")`、`androidTestImplementation("androidx.test:runner:1.5.2")`；`defaultConfig` 增加 `testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"` |
| `mobile/app/src/test/.../WavRoundTripTest.kt` | 新增，3 个用例，移植自 `WavSmoke.kt` |
| `mobile/app/src/test/.../LastAudioStoreTest.kt` | 新增，3 个用例，移植自 `LastAudioSmoke.kt`（用 `TemporaryFolder` 替代「调用方传入全新目录」） |
| `mobile/app/src/test/.../CoordinatorPlanTest.kt` | 新增，5 个用例，取自 `CoordinatorSmoke.kt` 的 LOCAL 与故障路径 |
| `mobile/app/src/androidTest/.../WavInstrumentedTest.kt` | 新增，2 个用例，设备端 WAV 编解码与 last.wav 持久化 |
| `server/requirements.txt` | 新增，固定 Python 3.11 依赖版本 |

原有 4 个 `fun main(args: Array<String>)` 形式的 smoke **保持原样未动**，避免影响已有证据；新增用例与它们逻辑同源。

## 结果

### JVM 单元测试

```
$env:JAVA_HOME="D:\Java\jdk-17.0.21+9"
cd D:\Computation_Partitioning\SA-lab\mobile
D:\gradle-8.2\bin\gradle.bat :app:testDebugUnitTest --no-daemon --console=plain
```

| 测试套 | 用例 | 失败 | 错误 | 耗时 |
| --- | --- | --- | --- | --- |
| `CoordinatorPlanTest` | 5 | 0 | 0 | 0.358 s |
| `WavRoundTripTest` | 3 | 0 | 0 | 0.007 s |
| `LastAudioStoreTest` | 3 | 0 | 0 | 0.034 s |
| **合计** | **11** | **0** | **0** | — |

构建结果：`BUILD SUCCESSFUL in 21s`。结果文件位于 `mobile/app/build/test-results/testDebugUnitTest/`，共 3 个 XML；改动前该目录只有 0 字节的 `output.bin`/`results.bin`，没有任何 XML。

### Python 测试

```
$env:PYTHONPATH="D:\Computation_Partitioning\SA-lab"
cd D:\Computation_Partitioning\SA-lab
.venv\Scripts\python.exe -m unittest discover -s server\tests
```

`Ran 34 tests in 9.174s` / `OK`。

装 `fastapi` 之前的状态是 `Ran 23 tests in 17.883s` / `FAILED (errors=3)`，三个 error 均为 `No module named 'fastapi'`（`server/app.py` → `server/gateway/service.py:10`）。

**注意：不要给 `discover` 加 `-t`**，否则报 `ImportError: Start directory is not importable`（`server/tests` 缺 `__init__.py`）。

### androidTest

```
gradle :app:assembleDebugAndroidTest
```

`BUILD SUCCESSFUL in 23s`，测试 APK 已生成。

**但它没有运行过。** `adb devices -l` 输出 `List of devices attached` 后无设备，本机当前没有连接真机。因此本文件只能声明「androidTest 可编译」，不能声明「设备端通过」。真机运行需 `gradle :app:connectedDebugAndroidTest`。

## 边界与未完成

1. **REMOTE 与 MANUAL_MIXED 未进 JVM 用例。** `RemoteExecutor` 依赖 `org.json` 与真实 HTTP，而 `src/test` 下 `org.json` 会被 `android.jar` 的 throw-stub 覆盖，因此 `CoordinatorPlanTest` 只跑 LOCAL 与故障路径，remote 用回落到本地的 stub 代替。REMOTE 的端到端验证必须放到 androidTest 或真机联调。
2. **`ExperimentSmoke` 未转 JUnit。** 它需要 `<dir>/samples.json`、`device-info.json`、`valid.wav`、`LOCAL.json`、`REMOTE.json`、`MANUAL_MIXED.json` 六个 fixture 文件，仓库内全库搜索 `fixture-valid` 只命中该 smoke 自身，没有任何 fixture 生成脚本。缺这套 fixture，强行转 JUnit 只会制造一个跑不起来的用例，因此本次保留原样，待 fixture 补齐后再转。
3. **androidTest 只有 2 个 WAV 用例。** 端到端录音→VAD→ASR→编码→匹配的冒烟需要真实模型包（约 1.8 GB）与设备授权流程，不在本次范围。
4. **11 个 JVM 用例不等于 S1 出口。** 它们只用 fixture 数据，不覆盖真实模型、真机录音、权限、取消后的实际文件状态。

## 与既有证据的关系

`evidence/`（Release v0.3.0 交付包）里的 `jvm-tests.txt`、`python-tests-final.txt` 来自组员机器，测试规模随阶段为 8 → 12 → 15 → 17 → 29 → 34。本次新增的 11 个 JVM 用例与那批**不是同一套用例**，两边的数字不能相加，也不能互相替代。
