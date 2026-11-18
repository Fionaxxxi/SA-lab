package com.example.interviewfeedback.transport

import com.example.interviewfeedback.application.*
import com.example.interviewfeedback.application.Module
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

private val HASH = Regex("[0-9a-f]{64}")
private fun JSONObject.text(key: String): String {
    val value = get(key)
    require(value is String && value.isNotBlank()) { "$key 必须是非空字符串" }
    return value
}
private fun JSONObject.number(key: String): Double {
    val value = get(key)
    require(value is Number && value.toDouble().isFinite()) { "$key 必须是有限数值" }
    return value.toDouble()
}
private fun JSONObject.integer(key: String): Int {
    val value = number(key)
    require(value >= 0 && value <= Int.MAX_VALUE && value % 1 == 0.0)
    return value.toInt()
}
private fun JSONObject.fields(required: Set<String>, optional: Set<String> = emptySet()) {
    val names = keys().asSequence().toSet()
    require(names.containsAll(required) && (names - required - optional).isEmpty()) { "配置字段缺失或包含未知字段" }
}

data class RunDefinition(val raw: String, val sha256: String, val runId: String, val condition: String,
    val source: InputSource, val durationSeconds: Double, val keypointCount: Int,
    val sampleManifestSha256: String, val plan: ExecutionPlan, val modelManifestSha256: String,
    val apkVersion: String?, val apkCommit: String?, val deviceModel: String,
    val androidVersion: String?, val abi: String?)
data class RegisteredSample(val id: String, val topicId: String, val split: String, val sha256: String,
    val effective: Boolean, val keypoints: List<Keypoint>, val reviewed: Boolean)
data class SampleCatalog(val raw: String, val sha256: String, val samples: List<RegisteredSample>)
data class ExperimentRuntime(val deviceId: String, val model: String, val androidVersion: String,
    val abi: String, val apkVersion: String, val apkCommit: String, val modelManifestSha256: String,
    val modelVersion: String, val configVersion: String)
data class BoundExperiment(val runId: String, val sample: RegisteredSample, val plan: ExecutionPlan, val link: ExperimentLink)

object ExperimentFiles {
    fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 255) }
    private fun decode(bytes: ByteArray): String = Charsets.UTF_8.newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .decode(java.nio.ByteBuffer.wrap(bytes)).toString().removePrefix("\uFEFF")

    fun run(bytes: ByteArray): RunDefinition {
        val raw = decode(bytes)
        val data = JSONObject(raw)
        data.fields(setOf("schema_version", "run_id", "measurement_version", "condition", "device", "network", "input", "runtime"))
        require(data.integer("schema_version") == 1 && data.text("measurement_version") == "measurement-v1")
        val condition = data.text("condition")
        require(condition in setOf("FIXTURE", "FORMAL"))
        val device = data.getJSONObject("device")
        device.fields(setOf("device_id", "model", "android_version", "abi", "power_mode", "charging", "battery_percent", "temperature_c"))
        for (key in listOf("android_version", "abi", "power_mode")) if (!device.isNull(key)) device.text(key)
        if (!device.isNull("charging")) require(device.get("charging") is Boolean)
        if (!device.isNull("battery_percent")) require(device.number("battery_percent") in 0.0..100.0)
        if (!device.isNull("temperature_c")) device.number("temperature_c")
        val network = data.getJSONObject("network")
        network.fields(setOf("mode", "actual_bandwidth_mbps", "actual_rtt_ms", "profile_id"))
        require(network.text("mode") in if (condition == "FORMAL") setOf("OFFLINE", "WIFI", "SHAPED") else setOf("OFFLINE", "WIFI", "SHAPED", "LOOPBACK"))
        for (key in listOf("actual_bandwidth_mbps", "actual_rtt_ms")) if (!network.isNull(key)) require(network.number(key) >= 0)
        if (!network.isNull("profile_id")) network.text("profile_id")
        val input = data.getJSONObject("input")
        input.fields(setOf("source", "duration_s", "keypoint_count", "sample_manifest_sha256", "topic_set"))
        val duration = input.number("duration_s")
        require(duration in 0.0..60.0)
        val count = input.integer("keypoint_count")
        require(count > 0)
        if (!input.isNull("topic_set")) input.text("topic_set")
        val sampleHash = input.text("sample_manifest_sha256")
        require(HASH.matches(sampleHash)) { "请填写实际样本清单 SHA256" }
        val runtime = data.getJSONObject("runtime")
        runtime.fields(setOf("plan_version", "model_version", "config_version", "apk_commit", "service_commit",
            "model_manifest_sha256", "apk_version", "warmup", "cache_policy", "mode"), setOf("remote_modules"))
        require(runtime.text("warmup") in setOf("COLD", "WARM"))
        require(runtime.text("cache_policy") in if (condition == "FORMAL") setOf("DISABLED", "FIXED") else setOf("DISABLED", "FIXED", "FIXTURE"))
        for (key in listOf("apk_commit", "service_commit")) if (!runtime.isNull(key))
            require(runtime.text(key).matches(Regex("[0-9a-f]{7,64}")))
        val modelHash = runtime.text("model_manifest_sha256")
        require(HASH.matches(modelHash))
        val apkVersion = if (runtime.isNull("apk_version")) null else runtime.text("apk_version")
        val apkCommit = if (runtime.isNull("apk_commit")) null else runtime.text("apk_commit")
        if (condition == "FORMAL") require(apkVersion != null && apkCommit != null)
        val mode = PlanMode.valueOf(runtime.text("mode"))
        if (runtime.has("remote_modules")) require(runtime.get("remote_modules") is JSONArray)
        val remote = runtime.optJSONArray("remote_modules")?.let { array ->
            val nodes = (0 until array.length()).map { Module.valueOf(array.getString(it)) }
            require(nodes.size == nodes.toSet().size)
            nodes.toSet()
        } ?: when (mode) {
            PlanMode.LOCAL -> emptySet()
            PlanMode.REMOTE -> setOf(Module.M1, Module.M2, Module.M3, Module.M4)
            PlanMode.MANUAL_MIXED -> error("混合模式须提供 remote_modules")
        }
        val plan = ExecutionPlan(runtime.text("plan_version"), device.text("device_id"), runtime.text("model_version"),
            runtime.text("config_version"), mode, remote)
        return RunDefinition(raw, sha256(bytes), data.text("run_id"), condition, InputSource.valueOf(input.text("source")),
            duration, count, sampleHash, plan, modelHash, apkVersion, apkCommit, device.text("model"),
            if (device.isNull("android_version")) null else device.text("android_version"),
            if (device.isNull("abi")) null else device.text("abi"))
    }

    fun samples(bytes: ByteArray): SampleCatalog {
        val raw = decode(bytes)
        val array = JSONArray(raw)
        require(array.length() in 1..10000) { "样本清单必须包含样本" }
        val samples = (0 until array.length()).map { index ->
            val row = array.getJSONObject(index)
            val points = row.getJSONArray("keypoints")
            val keys = (0 until points.length()).map { i -> points.getJSONObject(i).let {
                Keypoint(it.text("keypoint_id"), it.text("text")) } }
            require(keys.isNotEmpty() && keys.map { it.id }.distinct().size == keys.size)
            val effective = row.get("effective_input")
            require(effective is Boolean) { "样本 effective_input 须为 true 或 false" }
            val hash = row.text("sha256")
            require(HASH.matches(hash)) { "样本 SHA256 未填写" }
            val split = row.text("split")
            require(split in setOf("calibration", "evaluation"))
            val reviewed = row.opt("consent") == true && row.optString("reference_text").isNotBlank() &&
                row.optString("annotator").isNotBlank() && row.optString("reviewer").isNotBlank() &&
                row.optString("annotator").trim() != row.optString("reviewer").trim() &&
                (0 until points.length()).all { points.getJSONObject(it).opt("expected_covered") is Boolean }
            RegisteredSample(row.text("sample_id"), row.text("topic_id"), split, hash, effective, keys, reviewed)
        }
        require(samples.map { it.id }.distinct().size == samples.size) { "样本编号重复" }
        require(samples.groupBy { it.topicId }.values.all { rows -> rows.map { it.split }.distinct().size == 1 }) {
            "同一题目不能跨校准集和评价集" }
        return SampleCatalog(raw, sha256(bytes), samples)
    }

    fun bind(run: RunDefinition, catalog: SampleCatalog, selectedId: String?, source: InputSource,
             wavSha256: String?, actual: ExperimentRuntime): BoundExperiment {
        require(run.source == source) { "输入来源与运行配置不一致" }
        require(run.sampleManifestSha256 == catalog.sha256) { "样本清单与运行配置哈希不一致" }
        require(run.plan.deviceId == actual.deviceId && run.deviceModel == actual.model &&
            (run.androidVersion == null || run.androidVersion == actual.androidVersion) &&
            (run.abi == null || run.abi == actual.abi)) { "设备与运行配置不一致，请导出本机信息重新生成配置" }
        require(run.plan.modelVersion == actual.modelVersion && run.plan.configVersion == actual.configVersion &&
            run.modelManifestSha256 == actual.modelManifestSha256) { "模型或配置版本不一致" }
        require((run.apkVersion == null || run.apkVersion == actual.apkVersion) &&
            (run.apkCommit == null || actual.apkCommit.startsWith(run.apkCommit))) { "APK 版本与运行配置不一致" }
        if (run.condition == "FORMAL") {
            require(actual.apkCommit.matches(Regex("[0-9a-f]{40,64}"))) { "正式实验须使用有源码版本的 APK" }
            require(catalog.samples.size >= 30 && catalog.samples.all { it.reviewed } &&
                catalog.samples.map { it.split }.toSet() == setOf("calibration", "evaluation")) {
                "正式实验需至少 30 条已标注复核、分组的真实样本清单" }
        }
        val sample = if (selectedId != null) catalog.samples.single { it.id == selectedId } else {
            require(source == InputSource.IMPORT) { "录音实验须先选择登记样本" }
            val candidates = catalog.samples.filter { it.sha256 == wavSha256 }
            require(candidates.size == 1) { "WAV 无唯一匹配样本，请核对清单或明确选择样本" }
            candidates.single()
        }
        if (source == InputSource.IMPORT) require(sample.sha256 == wavSha256) { "WAV 哈希与所选样本不一致" }
        require(sample.keypoints.size == run.keypointCount) { "参考要点数与运行配置不一致" }
        return BoundExperiment(run.runId, sample, run.plan, ExperimentLink(run.condition, run.sha256,
            catalog.sha256, sample.sha256, sample.topicId, sample.split, wavSha256))
    }

    fun checkAudio(run: RunDefinition, audio: Audio) {
        // Zero denotes variable duration. Actual samples are always logged.
        if (run.durationSeconds > 0 && kotlin.math.abs(audio.sampleCount / 16000.0 - run.durationSeconds) > 0.25)
            throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
    }
    fun link(value: ExperimentLink): JSONObject = json("condition" to value.condition,
        "run_config_sha256" to value.runConfigSha256, "sample_manifest_sha256" to value.sampleManifestSha256,
        "sample_sha256" to value.sampleSha256, "topic_id" to value.topicId, "split" to value.split,
        "actual_wav_sha256" to value.actualWavSha256)
    fun readLink(value: JSONObject) = ExperimentLink(value.getString("condition"), value.getString("run_config_sha256"),
        value.getString("sample_manifest_sha256"), value.getString("sample_sha256"), value.getString("topic_id"),
        value.getString("split"), if (value.isNull("actual_wav_sha256")) null else value.getString("actual_wav_sha256"))
}

class FileExperimentStore(private val directory: File) {
    init { require(directory.isDirectory || directory.mkdirs()) }
    @Synchronized fun saveRun(bytes: ByteArray): RunDefinition = ExperimentFiles.run(bytes).also {
        val frozen = File(directory, "runs/" + ExperimentFiles.sha256(it.runId.toByteArray(Charsets.UTF_8)) + ".json")
        if (frozen.exists()) require(JSONObject(frozen.readText(Charsets.UTF_8)).getString("run_config_sha256") == it.sha256) { "run_id 已冻结，请更换 run_id" }
        save("configs/" + it.sha256 + ".json", bytes)
    }
    @Synchronized fun saveSamples(bytes: ByteArray): SampleCatalog = ExperimentFiles.samples(bytes).also {
        save("samples/" + it.sha256 + ".json", bytes)
    }
    @Synchronized fun freeze(run: RunDefinition, catalog: SampleCatalog) {
        require(run.sampleManifestSha256 == catalog.sha256) { "样本清单与配置不一致" }
        val name = "runs/" + ExperimentFiles.sha256(run.runId.toByteArray(Charsets.UTF_8)) + ".json"
        val data = json("run_id" to run.runId, "run_config_sha256" to run.sha256,
            "sample_manifest_sha256" to catalog.sha256, "plan" to WireJson.plan(run.plan)).toString().toByteArray(Charsets.UTF_8)
        val path = File(directory, name)
        if (path.exists()) {
            val previous = JSONObject(path.readText(Charsets.UTF_8))
            require(previous.getString("run_config_sha256") == run.sha256 &&
                previous.getString("sample_manifest_sha256") == catalog.sha256) { "run_id 已冻结，请更换 run_id" }
        } else save(name, data)
    }
    @Synchronized fun export(events: File, output: java.io.OutputStream) {
        java.util.zip.ZipOutputStream(output).use { zip ->
            if (events.isFile) {
                zip.putNextEntry(java.util.zip.ZipEntry("events.jsonl"))
                events.inputStream().use { it.copyTo(zip) }; zip.closeEntry()
            }
            directory.walkTopDown().filter { it.isFile && it.extension == "json" }.forEach { file ->
                zip.putNextEntry(java.util.zip.ZipEntry("experiments/" + file.relativeTo(directory).invariantSeparatorsPath))
                file.inputStream().use { it.copyTo(zip) }; zip.closeEntry()
            }
        }
    }
    private fun save(name: String, bytes: ByteArray) {
        val target = File(directory, name)
        target.parentFile?.mkdirs()
        if (target.exists()) { require(target.readBytes().contentEquals(bytes)); return }
        val temporary = File.createTempFile("import-", ".tmp", target.parentFile)
        try {
            FileOutputStream(temporary).use { it.write(bytes); it.fd.sync() }
            Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE)
        } finally { temporary.delete() }
    }
}
