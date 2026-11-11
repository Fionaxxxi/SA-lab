package com.example.interviewfeedback.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Build
import android.widget.*
import com.example.interviewfeedback.application.*
import com.example.interviewfeedback.application.Module
import com.example.interviewfeedback.analysis.semantic.RealModules
import com.example.interviewfeedback.capture.*
import com.example.interviewfeedback.transport.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.zip.ZipInputStream

class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val recorder = InterviewAudioRecorder()
    private lateinit var display: TextView
    private lateinit var server: EditText
    private lateinit var token: EditText
    private lateinit var points: EditText
    private lateinit var mode: Spinner
    private var modules: RealModules? = null
    @Volatile private var coordinator: TaskCoordinator? = null
    private val busy = java.util.concurrent.atomic.AtomicBoolean(false)
    private val cancelled = java.util.concurrent.atomic.AtomicBoolean(false)
    private var recording = false
    private var latestAudio: Audio? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val page = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 20, 24, 20) }
        fun button(label: String, action: () -> Unit) {
            page.addView(Button(this).apply { text = label; setOnClickListener { action() } })
        }
        page.addView(TextView(this).apply { text = "如何组织社区反诈宣传" })
        points = EditText(this).apply {
            setText("调查居民需求\n组织分层宣传\n评估宣传效果")
            hint = "每行一个参考要点"
        }
        page.addView(points)
        mode = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity,
            android.R.layout.simple_spinner_dropdown_item, listOf("LOCAL", "REMOTE", "MANUAL_MIXED")) }
        page.addView(mode)
        server = EditText(this).apply { hint = "电脑服务地址"; setText("http://192.168.1.2:8000") }
        token = EditText(this).apply { hint = "实验访问凭据"; inputType = 129 }
        page.addView(server); page.addView(token)
        button("导入模型包 ZIP") { choose("application/zip", 11) }
        button("录音 / 停止并分析") {
            if (!recording) {
                if (busy.get()) { display.text = "请等待当前操作结束"; return@button }
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
                } else {
                    try { recorder.start(); recording = true; display.text = "录音中，最长 60 秒" }
                    catch (error: Exception) { display.text = "录音失败，请导入 WAV。 ${error.javaClass.simpleName}" }
                }
            } else {
                recording = false
                val submitted = System.nanoTime()
                analyze(InputSource.RECORDING, submitted) { recorder.stop() }
            }
        }
        button("导入 WAV 并分析") { choose("audio/*", 10) }
        button("取消当前任务") {
            cancelled.set(true)
            coordinator?.current()?.let { coordinator?.cancel(it.taskId) }
            display.text = "当前任务已取消"
        }
        button("导出最近 WAV") {
            if (latestAudio == null) { display.text = "尚无音频"; return@button }
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                type = "audio/wav"; putExtra(Intent.EXTRA_TITLE, "answer.wav"); addCategory(Intent.CATEGORY_OPENABLE)
            }, 12)
        }
        button("导出实验事件 JSONL") {
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                type = "application/json"; putExtra(Intent.EXTRA_TITLE, "events.jsonl"); addCategory(Intent.CATEGORY_OPENABLE)
            }, 13)
        }
        display = TextView(this)
        page.addView(display)
        setContentView(ScrollView(this).apply { addView(page) })
        worker.execute {
            val installed = File(filesDir, "models")
            val backup = File(filesDir, "models-backup")
            if (!installed.exists() && backup.exists()) check(backup.renameTo(installed))
            val journal = FileTaskJournal(File(filesDir, "tasks"))
            // Recover unfinished records on app launch even before models become available.
            coordinator = TaskCoordinator(ModuleExecutor { throw ModuleFailure(ErrorCode.MODEL_UNAVAILABLE) },
                ModuleExecutor { throw ModuleFailure(ErrorCode.REMOTE_UNREACHABLE) }, journal,
                JsonlEventSink(File(filesDir, "events.jsonl")))
        }
    }

    private fun choose(type: String, code: Int) {
        if (recording || busy.get()) { display.text = "请先结束当前录音或操作"; return }
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            this.type = type; addCategory(Intent.CATEGORY_OPENABLE)
        }, code)
    }

    private fun analyze(source: InputSource, submitted: Long, audio: () -> Audio) {
        val address = server.text.toString()
        val credential = token.text.toString()
        val selected = PlanMode.valueOf(mode.selectedItem.toString())
        val keypoints = points.text.toString().lines().map { it.trim() }.filter { it.isNotEmpty() }
            .mapIndexed { i, text -> Keypoint("k${i + 1}", text) }
        if (keypoints.isEmpty()) {
            if (source == InputSource.RECORDING) worker.execute { recorder.stop() }
            display.text = "请填写参考要点"; return
        }
        if (!busy.compareAndSet(false, true)) { display.text = "请等待当前操作结束"; return }
        cancelled.set(false)
        display.text = "分析中"
        worker.execute {
            try {
                val capturedAudio = audio().also { latestAudio = it }
                if (cancelled.get()) return@execute
                val directory = File(filesDir, "models")
                val manifest = JSONObject(File(directory, "manifest.json").readText())
                val local = if (selected == PlanMode.REMOTE) {
                    ModuleExecutor { throw ModuleFailure(ErrorCode.MODEL_UNAVAILABLE) }
                } else {
                    if (modules == null) modules = RealModules(directory)
                    LocalExecutor(checkNotNull(modules))
                }
                val remote = if (selected == PlanMode.LOCAL) {
                    ModuleExecutor { throw ModuleFailure(ErrorCode.REMOTE_UNREACHABLE) }
                } else RemoteExecutor(address.toHttpUrl(), credential)
                val engine = TaskCoordinator(local, remote, FileTaskJournal(File(filesDir, "tasks")),
                    JsonlEventSink(File(filesDir, "events.jsonl")))
                coordinator = engine
                val remoteNodes = when (selected) {
                    PlanMode.LOCAL -> emptySet()
                    PlanMode.REMOTE -> setOf(Module.M1, Module.M2, Module.M3, Module.M4)
                    PlanMode.MANUAL_MIXED -> setOf(Module.M2, Module.M3)
                }
                val plan = ExecutionPlan("manual-${selected.name}", Build.MODEL.replace(Regex("[^A-Za-z0-9._-]"), "-"),
                    manifest.getString("model_version"), manifest.getString("config_version"), selected, remoteNodes)
                if (cancelled.get()) return@execute
                val task = engine.begin(plan, source, "manual-${System.currentTimeMillis()}", "manual-input",
                    submittedAtNanos = submitted)
                if (cancelled.get()) engine.cancel(task.taskId)
                engine.run(task.taskId, keypoints, 120000) {
                    capturedAudio.also {
                        latestAudio = it
                        File(filesDir, "last.wav").outputStream().use { output -> WavPcmIO.write(it, output) }
                    }
                }
                runOnUiThread {
                    if (coordinator !== engine) return@runOnUiThread
                    val record = engine.current() ?: return@runOnUiThread
                    display.text = record.feedback?.let { feedback ->
                        feedback.transcript.fullText + "\n\n" + feedback.matches.values.joinToString("\n") {
                            "${it.keypointId} ${if (it.covered) "已覆盖" else "可能遗漏"} ${"%.3f".format(it.score)}\n依据 ${it.evidenceText}"
                        } + "\n执行归属 " + plan.assignments
                    } ?: "${record.status} ${record.error ?: ""}"
                    if (record.status == TaskStatus.SUCCEEDED) display.post {
                        if (worker.isShutdown || isDestroyed) return@post
                        val visible = System.nanoTime()
                        worker.execute { engine.markFeedbackVisible(record.taskId, record.attempt, visible) }
                    }
                }
            } catch (error: Throwable) {
                if (error is VirtualMachineError || error is ThreadDeath) throw error
                runOnUiThread { display.text = "执行失败，请核对模型包和配置。 ${error.javaClass.simpleName}" }
            } finally { busy.set(false) }
        }
    }

    override fun onActivityResult(code: Int, result: Int, data: Intent?) {
        super.onActivityResult(code, result, data)
        if (result != RESULT_OK) return
        val uri = data?.data ?: return
        when (code) {
            10 -> analyze(InputSource.IMPORT, System.nanoTime()) {
                checkNotNull(contentResolver.openInputStream(uri)).use(WavPcmIO::read)
            }
            11 -> {
                if (!busy.compareAndSet(false, true)) { display.text = "请等待当前操作结束"; return }
                worker.execute {
                try {
                    check(coordinator?.current()?.status !in setOf(TaskStatus.CREATED, TaskStatus.RUNNING))
                    modules?.close(); modules = null
                    val directory = File(filesDir, "models-staging")
                    directory.deleteRecursively()
                    directory.mkdirs()
                    ZipInputStream(checkNotNull(contentResolver.openInputStream(uri))).use { zip ->
                        var total = 0L
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
                                        total += count
                                        require(total <= 5L * 1024 * 1024 * 1024)
                                        output.write(buffer, 0, count)
                                    }
                                }
                            }
                        }
                    }
                    val checkManifest = JSONObject(File(directory, "manifest.json").readText())
                    RealModules.verifyArtifacts(directory, checkManifest)
                    val installed = File(filesDir, "models")
                    val backup = File(filesDir, "models-backup")
                    backup.deleteRecursively()
                    if (installed.exists()) check(installed.renameTo(backup))
                    if (!directory.renameTo(installed)) {
                        backup.renameTo(installed)
                        error("Cannot publish model directory")
                    }
                    backup.deleteRecursively()
                    runOnUiThread { display.text = "模型包已导入 ${checkManifest.getString("model_version")}" }
                } catch (error: Exception) {
                    runOnUiThread { display.text = "模型导入失败 ${error.javaClass.simpleName}" }
                } finally { busy.set(false) }
                }
            }
            12 -> worker.execute {
                latestAudio?.let { audio ->
                    checkNotNull(contentResolver.openOutputStream(uri)).use { WavPcmIO.write(audio, it) }
                }
            }
            13 -> worker.execute {
                val file = File(filesDir, "events.jsonl")
                if (file.isFile) checkNotNull(contentResolver.openOutputStream(uri)).use { output ->
                    file.inputStream().use { it.copyTo(output) }
                }
            }
        }
    }

    override fun onDestroy() {
        cancelled.set(true)
        coordinator?.current()?.let { coordinator?.cancel(it.taskId) }
        if (recording) { recording = false; worker.execute { recorder.stop() } }
        worker.execute { modules?.close(); modules = null }
        worker.shutdown()
        super.onDestroy()
    }
}
