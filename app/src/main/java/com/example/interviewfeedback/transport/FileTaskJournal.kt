package com.example.interviewfeedback.transport

import com.example.interviewfeedback.application.*
import com.example.interviewfeedback.application.Module
import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import org.json.JSONObject
import org.json.JSONArray

/** Construct once per app process using an app-private directory. */
class FileTaskJournal(private val directory: File) : TaskJournal {
    init { require(directory.isDirectory || directory.mkdirs()) }

    @Synchronized
    override fun save(record: TaskRecord) {
        val target = file(record.taskId)
        val data = json("task_id" to record.taskId, "attempt" to record.attempt, "status" to record.status.name,
            "plan" to WireJson.plan(record.plan), "input_source" to record.source.name,
            "run_id" to record.runId, "sample_id" to record.sampleId, "submitted_at_ms" to record.submittedAtMs,
            "error_code" to record.error?.name, "visible" to record.visible,
            "effective_input" to record.effectiveInput, "audio_samples" to record.audioSamples,
            "measurements" to JSONArray(record.measurements.map { measurementJson(it) }),
            "total_elapsed_ms" to record.totalElapsedMs, "feedback_elapsed_ms" to record.feedbackElapsedMs,
            "experiment" to record.experiment?.let(ExperimentFiles::link),
            "feedback" to record.feedback?.let {
                json("transcript" to WireJson.transcript(it.transcript), "matches" to WireJson.matches(it.matches))
            })
        val temporary = File.createTempFile("task-", ".tmp", directory)
        try {
            FileOutputStream(temporary).use { output ->
                output.write(data.toString().toByteArray(Charsets.UTF_8))
                output.fd.sync()
            }
            Files.move(temporary.toPath(), target.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } finally {
            temporary.delete()
        }
    }

    @Synchronized
    fun load(taskId: String): TaskRecord? =
        file(taskId).takeIf { it.isFile }?.let { decode(JSONObject(it.readText(Charsets.UTF_8))) }

    @Synchronized
    override fun unfinished(): List<TaskRecord> = checkNotNull(directory.listFiles()).mapNotNull { file ->
        if (!file.isFile || file.extension != "json") return@mapNotNull null
        val data = JSONObject(file.readText(Charsets.UTF_8))
        val status = TaskStatus.valueOf(data.getString("status"))
        if (status == TaskStatus.CREATED || status == TaskStatus.RUNNING) decode(data) else null
    }

    private fun file(taskId: String): File {
        require(taskId.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")))
        return File(directory, "$taskId.json")
    }

    private fun decode(data: JSONObject) = TaskRecord(
        taskId = data.getString("task_id"),
        plan = WireJson.readPlan(data.getJSONObject("plan")),
        source = InputSource.valueOf(data.getString("input_source")),
        runId = data.getString("run_id"),
        sampleId = data.getString("sample_id"),
        submittedAtMs = data.getLong("submitted_at_ms"),
        status = TaskStatus.valueOf(data.getString("status")),
        attempt = data.getInt("attempt"),
        feedback = data.optJSONObject("feedback")?.let {
            Feedback(WireJson.readTranscript(it.getJSONObject("transcript")),
                WireJson.readMatches(it.getJSONArray("matches")))
        },
        error = if (data.isNull("error_code")) null else ErrorCode.valueOf(data.getString("error_code")),
        visible = data.getBoolean("visible"),
        effectiveInput = if (data.isNull("effective_input")) null else data.getBoolean("effective_input"),
        audioSamples = if (data.isNull("audio_samples")) null else data.getInt("audio_samples"),
        measurements = data.optJSONArray("measurements")?.read(::readMeasurement) ?: emptyList(),
        totalElapsedMs = if (data.isNull("total_elapsed_ms")) null else data.getLong("total_elapsed_ms"),
        feedbackElapsedMs = if (data.isNull("feedback_elapsed_ms")) null else data.getLong("feedback_elapsed_ms"),
        experiment = data.optJSONObject("experiment")?.let(ExperimentFiles::readLink),
    )
}

/** Export this file for measurement. It contains no audio, raw text, token or server address. */
class JsonlEventSink(private val file: File) : EventSink {
    @Synchronized
    override fun append(event: TaskEvent) {
        val task = event.task
        val plan = task.plan
        val timing = event.timing
        val data = json("event_schema_version" to 1, "event" to event.event, "task_id" to task.taskId,
            "attempt" to task.attempt, "plan_version" to plan.planVersion, "mode" to plan.mode.name,
            "device_id" to plan.deviceId, "model_version" to plan.modelVersion,
            "config_version" to plan.configVersion, "run_id" to task.runId, "sample_id" to task.sampleId,
            "input_source" to task.source.name, "effective_input" to task.effectiveInput,
            "audio_samples" to task.audioSamples, "module_id" to event.module?.name,
            "executor" to event.executor?.name, "status" to event.status,
            "error_code" to event.error?.name, "elapsed_ms" to timing?.elapsedMs,
            "module_time_known" to timing?.moduleTimeKnown, "round_trip_ms" to timing?.roundTripMs,
            "serialize_ms" to timing?.encodeMs, "deserialize_ms" to timing?.decodeMs,
            "experiment" to task.experiment?.let(ExperimentFiles::link),
            "bytes_up" to (timing?.bytesUp ?: 0L), "bytes_down" to (timing?.bytesDown ?: 0L))
        file.appendText(data.toString() + "\n", Charsets.UTF_8)
    }
}

private fun measurementJson(value: ModuleMeasurement): JSONObject = value.timing.let {
    json("module_id" to value.module.name, "executor" to value.executor.name, "status" to value.status,
        "error_code" to value.error?.name, "elapsed_ms" to it.elapsedMs, "bytes_up" to it.bytesUp,
        "bytes_down" to it.bytesDown, "round_trip_ms" to it.roundTripMs, "serialize_ms" to it.encodeMs,
        "deserialize_ms" to it.decodeMs, "module_time_known" to it.moduleTimeKnown)
}
private fun readMeasurement(data: JSONObject) = ModuleMeasurement(Module.valueOf(data.getString("module_id")),
    Executor.valueOf(data.getString("executor")), data.getString("status"), Timing(data.getLong("elapsed_ms"),
        data.getLong("bytes_up"), data.getLong("bytes_down"),
        if (data.isNull("round_trip_ms")) null else data.getLong("round_trip_ms"),
        if (data.isNull("serialize_ms")) null else data.getLong("serialize_ms"),
        if (data.isNull("deserialize_ms")) null else data.getLong("deserialize_ms"), data.getBoolean("module_time_known")),
    if (data.isNull("error_code")) null else ErrorCode.valueOf(data.getString("error_code")))
