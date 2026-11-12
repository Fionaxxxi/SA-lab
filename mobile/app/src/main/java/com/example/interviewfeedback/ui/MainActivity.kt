package com.example.interviewfeedback.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Build
import android.os.BatteryManager
import android.os.PowerManager
import android.widget.*
import com.example.interviewfeedback.BuildConfig
import com.example.interviewfeedback.application.*
import com.example.interviewfeedback.application.Module
import com.example.interviewfeedback.analysis.semantic.RealModules
import com.example.interviewfeedback.capture.*
import com.example.interviewfeedback.transport.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONObject
import java.io.*
import java.util.UUID
import java.util.concurrent.Executors
import java.util.zip.ZipInputStream

class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val recorder = InterviewAudioRecorder()
    private lateinit var display: TextView
    private lateinit var timingDisplay: TextView
    private lateinit var experimentDisplay: TextView
    private lateinit var server: EditText
    private lateinit var token: EditText
    private lateinit var points: EditText
    private lateinit var mode: Spinner
    private lateinit var samplePicker: Spinner
    private lateinit var experiments: FileExperimentStore
    private lateinit var deviceId: String
    private var activeRun: RunDefinition? = null
    private var activeCatalog: SampleCatalog? = null
    private var visibleScheduled: String? = null
    private var modules: RealModules? = null
    @Volatile private var coordinator: TaskCoordinator? = null
    private val busy = java.util.concurrent.atomic.AtomicBoolean(true)
    private val initializing = java.util.concurrent.atomic.AtomicBoolean(true)
    private val cancelled = java.util.concurrent.atomic.AtomicBoolean(false)
    private var recording = false
    private lateinit var lastAudio: LastAudioStore
    private lateinit var statusBanner: TextView
    private lateinit var screen: MobileScreen

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        lastAudio = LastAudioStore(File(filesDir, "last.wav"))
        experiments = FileExperimentStore(File(filesDir, "experiments"))
        val preferences = getSharedPreferences("experiment", MODE_PRIVATE)
        deviceId = preferences.getString("device_id", null) ?: ("android-" + UUID.randomUUID()).also {
            preferences.edit().putString("device_id", it).apply()
        }
        val actions = mutableMapOf<String, () -> Unit>()
        screen = MobileScreen(this) { key -> actions[key]?.invoke() }
        display = screen.display; timingDisplay = screen.timings
        statusBanner = screen.status; points = screen.points; mode = screen.mode
        server = screen.server; token = screen.token
        experimentDisplay = screen.experiment; samplePicker = screen.samples
        fun button(label: String, action: () -> Unit) { actions[label] = action }
        samplePicker.apply {
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) {}
                override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                    activeCatalog?.samples?.getOrNull(position - 1)?.let {
                        if (activeRun != null) points.setText(it.keypoints.joinToString("\n") { key -> key.text })
                    }
                }
            }
        }
        button("导入运行配置 JSON") { choose("application/json", 14) }
        button("导入样本清单 JSON") { choose("application/json", 15) }
        button("退出实验模式") {
            if (recording || busy.get()) { setStatus("请先结束当前操作"); return@button }
            activeRun = null; activeCatalog = null
            preferences.edit().remove("active_run").remove("active_samples").apply()
            refreshExperiment()
        }
        button("导出本机及模型信息 JSON") { createExport("application/json", "device-info.json", 16) }
        button("导出完整实验记录 ZIP") { createExport("application/zip", "experiment-records.zip", 17) }
        button("导入模型包 ZIP") { choose("application/zip", 11) }
        button("录音 / 停止并分析") {
            if (!recording) {
                if (busy.get()) { setStatus("请等待当前操作结束"); return@button }
                if (!readyFor(InputSource.RECORDING)) return@button
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
                else try { recorder.start(); recording = true; screen.setRecording(true); setStatus("正在录音 · 再次点击停止并分析") }
                catch (error: Exception) { setStatus("录音失败，请导入 WAV。 " + error.javaClass.simpleName) }
            } else {
                recording = false; screen.setRecording(false)
                analyze(InputSource.RECORDING, System.nanoTime()) { prepared(recorder.stop()) }
            }
        }
        button("导入 WAV 并分析") { if (readyFor(InputSource.IMPORT)) choose("audio/*", 10) }
        button("取消当前任务") {
            cancelled.set(true)
            coordinator?.current()?.let { coordinator?.cancel(it.taskId) }
            setStatus("当前任务已取消")
        }
        button("导出最近 WAV") {
            if (!lastAudio.available()) setStatus("尚无已保存音频") else createExport("audio/wav", "answer.wav", 12)
        }
        button("导出实验事件 JSONL") { createExport("application/json", "events.jsonl", 13) }
        worker.execute {
            try {
                val installed = File(filesDir, "models")
                val backup = File(filesDir, "models-backup")
                if (!installed.exists() && backup.exists()) check(backup.renameTo(installed))
                coordinator = TaskCoordinator(ModuleExecutor { throw ModuleFailure(ErrorCode.MODEL_UNAVAILABLE) },
                    ModuleExecutor { throw ModuleFailure(ErrorCode.REMOTE_UNREACHABLE) }, FileTaskJournal(File(filesDir, "tasks")), eventSink())
                val directory = File(filesDir, "experiments")
                val run = preferences.getString("active_run", null)?.let {
                    require(it.matches(Regex("[0-9a-f]{64}")))
                    ExperimentFiles.run(File(directory, "configs/" + it + ".json").readBytes()) }
                val catalog = preferences.getString("active_samples", null)?.let {
                    require(it.matches(Regex("[0-9a-f]{64}")))
                    ExperimentFiles.samples(File(directory, "samples/" + it + ".json").readBytes()) }
                runOnUiThread { activeRun = run; activeCatalog = catalog; refreshExperiment(); setStatus(if (File(filesDir, "models/manifest.json").isFile) "就绪 · 模型清单已安装" else "就绪 · 请先导入模型包") }
            } catch (error: Exception) {
                runOnUiThread { setStatus("初始化失败，请重新导入配置。 " + error.javaClass.simpleName); refreshExperiment() }
            } finally { initializing.set(false); busy.set(false) }
        }
    }

    private fun setStatus(message: String) {
        if (isDestroyed) return
        statusBanner.text = message
    }

    private data class PreparedAudio(val audio: Audio, val wavSha256: String)
    private fun prepared(audio: Audio): PreparedAudio {
        val bytes = ByteArrayOutputStream().also { WavPcmIO.write(audio, it) }.toByteArray()
        return PreparedAudio(audio, ExperimentFiles.sha256(bytes))
    }
    private fun readBounded(input: InputStream, limit: Int = 8 * 1024 * 1024): ByteArray = input.use {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(65536)
        while (true) {
            val count = it.read(buffer)
            if (count < 0) break
            require(output.size().toLong() + count <= limit) { "文件超过大小上限" }
            output.write(buffer, 0, count)
        }
        output.toByteArray()
    }
    private fun refreshExperiment() {
        val run = activeRun
        val catalog = activeCatalog
        experimentDisplay.text = if (run == null && catalog == null) "普通模式 · 样本未登记，不进入正式实验" else
            "运行 " + (run?.runId ?: "待导入") + " · " + (run?.condition ?: "") +
                "\n样本清单 " + (catalog?.samples?.size ?: 0) + " 条 · 输入 " + (run?.source?.name ?: "待定")
        mode.isEnabled = run == null; points.isEnabled = run == null
        if (run != null) mode.setSelection(PlanMode.values().indexOf(run.plan.mode))
        samplePicker.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            listOf("导入 WAV 时按哈希自动匹配") + (catalog?.samples?.map { it.id + " · " + if (it.effective) "有效" else "无效" } ?: emptyList()))
    }
    private fun eventSink(): EventSink {
        val sink = JsonlEventSink(File(filesDir, "events.jsonl"))
        return EventSink { event ->
            sink.append(event)
            runOnUiThread {
                val engine = coordinator
                val task = engine?.current()
                if (!isDestroyed && engine != null && task?.taskId == event.task.taskId && task.attempt == event.task.attempt)
                    showRecord(engine, task)
            }
        }
    }
    private fun showRecord(engine: TaskCoordinator, record: TaskRecord) {
        if (coordinator !== engine) return
        timingDisplay.text = TaskMeasurements.text(record)
        if (record.feedback == null) display.text = "分析状态：" + record.status.name + (record.error?.let { " · " + it.name } ?: "")
        screen.render(record)
        val key = record.taskId + ":" + record.attempt
        if (record.status == TaskStatus.SUCCEEDED && !record.visible && visibleScheduled != key) {
            visibleScheduled = key
            val listener = object : android.view.ViewTreeObserver.OnDrawListener {
                private var posted = false
                override fun onDraw() {
                    if (posted || !display.isShown || display.windowVisibility != android.view.View.VISIBLE) return
                    posted = true
                    display.post {
                        if (display.viewTreeObserver.isAlive) display.viewTreeObserver.removeOnDrawListener(this)
                        if (worker.isShutdown || isDestroyed || coordinator !== engine) return@post
                        val visible = System.nanoTime()
                        worker.execute { engine.markFeedbackVisible(record.taskId, record.attempt, visible) }
                    }
                }
            }
            display.viewTreeObserver.addOnDrawListener(listener)
            display.invalidate()
        }
    }
    private fun readyFor(source: InputSource): Boolean {
        val run = activeRun; val catalog = activeCatalog
        val error = when {
            run == null && catalog == null -> null
            run == null || catalog == null -> "请同时导入运行配置和样本清单，或退出实验模式"
            run.source != source -> "输入来源与运行配置不一致"
            run.sampleManifestSha256 != catalog.sha256 -> "样本清单与运行配置哈希不一致"
            source == InputSource.RECORDING && samplePicker.selectedItemPosition == 0 -> "录音实验须先选择登记样本"
            else -> null
        }
        if (error != null) setStatus(error)
        return error == null
    }
    private fun choose(type: String, code: Int) {
        if (recording || busy.get()) { setStatus("请先结束当前录音或操作"); return }
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            this.type = type; addCategory(Intent.CATEGORY_OPENABLE)
        }, code)
    }
    private fun createExport(type: String, filename: String, code: Int) {
        if (recording || busy.get() || coordinator?.current()?.let { it.status == TaskStatus.SUCCEEDED && !it.visible } == true) {
            setStatus("请等待当前操作及反馈展示完成"); return
        }
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            this.type = type; putExtra(Intent.EXTRA_TITLE, filename); addCategory(Intent.CATEGORY_OPENABLE)
        }, code)
    }
    private fun runtimeInfo(bytes: ByteArray): ExperimentRuntime {
        val manifest = JSONObject(bytes.toString(Charsets.UTF_8))
        return ExperimentRuntime(deviceId, Build.MODEL, Build.VERSION.RELEASE,
            Build.SUPPORTED_ABIS.firstOrNull { it == "arm64-v8a" } ?: Build.SUPPORTED_ABIS.first(),
            BuildConfig.VERSION_NAME, BuildConfig.SOURCE_REVISION, ExperimentFiles.sha256(bytes),
            manifest.getString("model_version"), manifest.getString("config_version"))
    }
    private fun deviceInfo(): JSONObject {
        val info = runtimeInfo(File(filesDir, "models/manifest.json").readBytes())
        val battery = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val temperature = battery?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        fun objectOf(vararg pairs: Pair<String, Any?>) = JSONObject().also { obj ->
            pairs.forEach { obj.put(it.first, it.second ?: JSONObject.NULL) } }
        return objectOf("device_info_schema_version" to 1,
            "device" to objectOf("device_id" to info.deviceId, "model" to info.model, "android_version" to info.androidVersion,
                "abi" to info.abi, "power_mode" to if ((getSystemService(POWER_SERVICE) as PowerManager).isPowerSaveMode) "POWER_SAVE" else "NORMAL",
                "charging" to if (status < 0) null else (status in setOf(BatteryManager.BATTERY_STATUS_CHARGING, BatteryManager.BATTERY_STATUS_FULL)),
                "battery_percent" to if (level >= 0 && scale > 0) level * 100.0 / scale else null,
                "temperature_c" to if (temperature != Int.MIN_VALUE) temperature / 10.0 else null),
            "runtime" to objectOf("apk_version" to info.apkVersion,
                "apk_commit" to info.apkCommit.takeIf { it.matches(Regex("[0-9a-f]{40,64}")) },
                "model_version" to info.modelVersion, "config_version" to info.configVersion,
                "model_manifest_sha256" to info.modelManifestSha256))
    }

    private fun analyze(source: InputSource, submitted: Long, audio: () -> PreparedAudio) {
        val address = server.text.toString(); val credential = token.text.toString()
        val run = activeRun; val catalog = activeCatalog
        val selection = catalog?.samples?.getOrNull(samplePicker.selectedItemPosition - 1)?.id
        val selected = PlanMode.valueOf(mode.selectedItem.toString())
        val manualPoints = points.text.toString().lines().map { it.trim() }.filter { it.isNotEmpty() }
            .mapIndexed { i, text -> Keypoint("k" + (i + 1), text) }
        if (!busy.compareAndSet(false, true)) { setStatus("请等待当前操作结束"); return }
        cancelled.set(false); timingDisplay.text = "准备输入和运行配置"; screen.clearFeedback(); setStatus("正在分析 · 首次加载模型可能需要稍等")
        worker.execute {
            try {
                val prepStarted = System.nanoTime()
                val captured = audio()
                val prepMs = (System.nanoTime() - prepStarted) / 1_000_000L
                if (cancelled.get()) return@execute
                require((run == null) == (catalog == null)) { "请同时导入运行配置和样本清单，或退出实验模式" }
                val directory = File(filesDir, "models")
                val info = runtimeInfo(File(directory, "manifest.json").readBytes())
                val bound = if (run != null && catalog != null) {
                    ExperimentFiles.bind(run, catalog, selection, source, captured.wavSha256, info).also { experiments.freeze(run, catalog) }
                } else null
                val remoteNodes = when (selected) {
                    PlanMode.LOCAL -> emptySet()
                    PlanMode.REMOTE -> setOf(Module.M1, Module.M2, Module.M3, Module.M4)
                    PlanMode.MANUAL_MIXED -> setOf(Module.M2, Module.M3)
                }
                val plan = bound?.plan ?: ExecutionPlan("manual-" + selected.name, deviceId,
                    info.modelVersion, info.configVersion, selected, remoteNodes)
                val keypoints = bound?.sample?.keypoints ?: manualPoints
                require(keypoints.isNotEmpty()) { "请填写参考要点" }
                val local = if (plan.mode == PlanMode.REMOTE) ModuleExecutor { throw ModuleFailure(ErrorCode.MODEL_UNAVAILABLE) }
                else { if (modules == null) modules = RealModules(directory); LocalExecutor(checkNotNull(modules)) }
                val remote = if (plan.mode == PlanMode.LOCAL) ModuleExecutor { throw ModuleFailure(ErrorCode.REMOTE_UNREACHABLE) }
                    else RemoteExecutor(address.toHttpUrl(), credential)
                val engine = TaskCoordinator(local, remote, FileTaskJournal(File(filesDir, "tasks")), eventSink())
                coordinator = engine
                if (cancelled.get()) return@execute
                val task = engine.begin(plan, source, bound?.runId ?: ("manual-" + UUID.randomUUID()),
                    bound?.sample?.id ?: ("unregistered-" + UUID.randomUUID()), bound?.sample?.effective,
                    submittedAtNanos = submitted, experiment = bound?.link)
                runOnUiThread { screen.setReference(keypoints); if (bound != null) points.setText(keypoints.joinToString("\n") { it.text }) }
                if (cancelled.get()) engine.cancel(task.taskId)
                engine.run(task.taskId, keypoints, 120000, priorAudioPreparationMs = prepMs) {
                    if (run != null) ExperimentFiles.checkAudio(run, captured.audio)
                    lastAudio.save(captured.audio)
                    captured.audio
                }
                runOnUiThread { if (!isDestroyed && coordinator === engine) engine.current()?.let { showRecord(engine, it) } }
            } catch (error: Throwable) {
                if (error is VirtualMachineError || error is ThreadDeath) throw error
                runOnUiThread { setStatus("执行或配置校验失败：" + (error.message ?: error.javaClass.simpleName)) }
            } finally { busy.set(false) }
        }
    }

    override fun onActivityResult(code: Int, result: Int, data: Intent?) {
        super.onActivityResult(code, result, data)
        if (result != RESULT_OK) return
        val uri = data?.data ?: return
        if (initializing.get()) {
            worker.execute { runOnUiThread { if (!isDestroyed) onActivityResult(code, result, data) } }
            return
        }
        if (code == 10) {
            analyze(InputSource.IMPORT, System.nanoTime()) {
                val bytes = readBounded(checkNotNull(contentResolver.openInputStream(uri)))
                PreparedAudio(ByteArrayInputStream(bytes).use(WavPcmIO::read), ExperimentFiles.sha256(bytes))
            }
            return
        }
        if (!busy.compareAndSet(false, true)) { setStatus("请等待当前操作结束"); return }
        worker.execute {
            try {
                runOnUiThread { setStatus(if (code == 11) "正在导入模型，请保持应用在前台，不要重复点击" else "正在处理，请稍候") }
                when (code) {
                    11 -> importModels(checkNotNull(contentResolver.openInputStream(uri)))
                    12 -> checkNotNull(contentResolver.openOutputStream(uri)).use { lastAudio.export(it) }
                    13 -> checkNotNull(contentResolver.openOutputStream(uri)).use { output ->
                        val file = File(filesDir, "events.jsonl")
                        if (file.isFile) file.inputStream().use { it.copyTo(output) }
                    }
                    14 -> {
                        val run = experiments.saveRun(readBounded(checkNotNull(contentResolver.openInputStream(uri))))
                        getSharedPreferences("experiment", MODE_PRIVATE).edit().putString("active_run", run.sha256).apply()
                        runOnUiThread { activeRun = run; refreshExperiment() }
                    }
                    15 -> {
                        val catalog = experiments.saveSamples(readBounded(checkNotNull(contentResolver.openInputStream(uri))))
                        getSharedPreferences("experiment", MODE_PRIVATE).edit().putString("active_samples", catalog.sha256).apply()
                        runOnUiThread { activeCatalog = catalog; refreshExperiment() }
                    }
                    16 -> checkNotNull(contentResolver.openOutputStream(uri)).use { it.write(deviceInfo().toString(2).toByteArray(Charsets.UTF_8)) }
                    17 -> experiments.export(File(filesDir, "events.jsonl"), checkNotNull(contentResolver.openOutputStream(uri)))
                }
                val completed = when (code) {
                    11 -> "模型导入成功，文件已校验，可选择 LOCAL 开始分析"
                    12 -> "WAV 导出成功，请在所选保存位置查看 answer.wav"
                    13 -> "事件日志导出成功"
                    else -> "导入或导出完成"
                }
                runOnUiThread { setStatus(completed) }
            } catch (error: Exception) {
                runOnUiThread { setStatus("操作失败：" + (error.message ?: error.javaClass.simpleName)) }
            } finally { busy.set(false) }
        }
    }
    private fun importModels(input: InputStream) {
        modules?.close(); modules = null
        val directory = File(filesDir, "models-staging")
        directory.deleteRecursively(); directory.mkdirs()
        ZipInputStream(input).use { zip ->
            var total = 0L
            var reported = 0L
            while (true) {
                val entry = zip.nextEntry ?: break
                val target = File(directory, entry.name).canonicalFile
                require(target.toPath().startsWith(directory.canonicalFile.toPath()))
                if (entry.isDirectory) target.mkdirs() else {
                    target.parentFile?.mkdirs()
                    target.outputStream().use { output ->
                        val buffer = ByteArray(65536)
                        while (true) {
                            val count = zip.read(buffer)
                            if (count < 0) break
                            total += count; require(total <= 5L * 1024 * 1024 * 1024)
                            if (total - reported >= 64L * 1024 * 1024) {
                                reported = total
                                val mb = total / (1024 * 1024)
                                runOnUiThread { setStatus("正在解压模型，已处理 " + mb + " MB，请保持应用在前台") }
                            }
                            output.write(buffer, 0, count)
                        }
                    }
                }
            }
        }
        val manifest = JSONObject(File(directory, "manifest.json").readText(Charsets.UTF_8))
        runOnUiThread { setStatus("解压完成，正在逐个校验模型文件，请等待") }
        RealModules.verifyArtifacts(directory, manifest)
        val installed = File(filesDir, "models"); val backup = File(filesDir, "models-backup")
        backup.deleteRecursively()
        if (installed.exists()) check(installed.renameTo(backup))
        if (!directory.renameTo(installed)) { backup.renameTo(installed); error("Cannot publish models") }
        backup.deleteRecursively()
    }
    override fun onDestroy() {
        screen.close()
        cancelled.set(true)
        coordinator?.current()?.let { coordinator?.cancel(it.taskId) }
        if (recording) { recording = false; worker.execute { recorder.stop() } }
        worker.execute { modules?.close(); modules = null }
        worker.shutdown()
        super.onDestroy()
    }
}
