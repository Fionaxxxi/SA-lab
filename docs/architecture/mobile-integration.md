# 手机端协调器接入

`application/` 提供类型、执行计划、LocalExecutor 和 TaskCoordinator。`transport/` 提供 OkHttp RemoteExecutor、私有 JSON 任务文件和 JSONL 日志。代码最低 API 26，传输 JSON 使用 Android 内置 `org.json`，OkHttp 用 4.12.0 验证。应用的 Gradle、Manifest、Android 调试网络配置与 ViewModel 入口由客户端分支接入。

1. 应用进程启动时构造一个 TaskCoordinator。传入 LocalExecutor 包装刘、彭的 LocalModules 实现、RemoteExecutor，以及以 `filesDir` 为根的 FileTaskJournal 与 JsonlEventSink。离线配置的 remote 可以注入会拒绝调用的执行器。
2. 停止录音或提交导入时取 `System.nanoTime()`，用后台执行器调用 `begin(..., submittedAtNanos = value)`。将样本/运行 ID 与预先分类的有效输入传入，再调 `run(taskId, keypoints, budgetMs) { ... }`。prepareAudio 由客户端返回去 WAV 头的 PCM 和采样点数。
3. 界面在 ViewModel 中通过 `current()` 读取当前状态快照，按 taskId/attempt 展示。绘制完整反馈后立即取 `System.nanoTime()`，后台调用 `markFeedbackVisible` 并传入该时间。取消调用 `cancel(taskId)`，已在运行的工作退出后才接纳下一任务。取消前已保存的成功结果照常保留。
4. 真机应用把本地模块错误映射为 ModuleFailure。远程请求按计划独立发出。异常时显示当前终态及错误码。任务记录只留应用私有目录，实验导出使用 JSONL 事件文件和独立 run 配置。

## JVM 复跑

在 JDK 17 和 Kotlin 1.9.22 下，将 `application/`、`transport/`、`CoordinatorSmoke.kt` 作为同一编译单元，使用 `-jvm-target 17`。编译和运行类路径包含 Kotlin 标准库、OkHttp 4.12.0、Okio JVM 3.6.0 和 JVM 版 org.json 20240303。将 Kotlin compiler-embeddable、daemon-embeddable、script-runtime、stdlib（均为 1.9.22）、kotlin-reflect 1.6.10、trove4j 1.0.20200330、annotations 13.0 及上述依赖 JAR 放在同一目录，可直接从仓库根目录运行 Windows 脚本：

```powershell
./server/tests/run-jvm-smoke.ps1 -KotlinJars '<JAR 目录>' -Java '<JDK 17 java.exe>' -Python '<项目 venv python.exe>' -Evidence .evidence/ljx-jvm
```

脚本启动随机端口的 127.0.0.1 临时服务，核对三种执行计划、取消、旧 attempt、重启和真实 HTTP 正文字节。运行目录应是新目录。JVM 回环证据可用于接口复查，Android 编译、录音、权限、模型和两机表现需在 APK 上验收。
