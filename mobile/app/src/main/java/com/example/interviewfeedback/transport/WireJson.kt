package com.example.interviewfeedback.transport

import com.example.interviewfeedback.application.*
import java.util.Base64
import org.json.JSONArray
import org.json.JSONObject

internal fun json(vararg fields: Pair<String, Any?>): JSONObject =
    JSONObject().also { target -> fields.forEach { (key, value) -> target.put(key, value ?: JSONObject.NULL) } }

internal fun <T> JSONArray.read(convert: (JSONObject) -> T): List<T> =
    (0 until length()).map { convert(getJSONObject(it)) }

internal object WireJson {
    fun request(request: ModuleRequest): JSONObject = request.id.run {
        json("schema_version" to schemaVersion, "task_id" to taskId, "attempt" to attempt,
            "module_id" to module.name, "plan_version" to planVersion, "model_version" to modelVersion,
            "config_version" to configVersion, "remaining_budget_ms" to request.remainingBudgetMs,
            "payload" to payload(request.payload))
    }

    fun identity(value: JSONObject): CallId = CallId(
        value.getString("task_id"), value.getInt("attempt"), Module.valueOf(value.getString("module_id")),
        value.getString("plan_version"), value.getString("model_version"), value.getString("config_version"),
        value.getInt("schema_version"),
    )

    private fun payload(input: ModuleInput): JSONObject = when (input) {
        is Audio -> json("audio" to json("sample_rate_hz" to 16000, "channels" to 1,
            "sample_format" to "s16le", "sample_count" to input.sampleCount, "pcm_b64" to base64(input.pcm)))
        is Segments -> json("segments" to JSONArray(input.values.map {
            json("segment_id" to it.id, "start_sample" to it.start, "end_sample" to it.end,
                "pcm_b64" to base64(it.pcm))
        }))
        is EncodeInput -> json("transcript" to transcript(input.transcript), "keypoints" to
            JSONArray(input.keypoints.map { json("keypoint_id" to it.id, "text" to it.text) }))
        is Embeddings -> json("embeddings" to json("dimension" to input.dimension,
            "answer_sentences" to JSONArray(input.sentences.map {
                json("sentence_id" to it.id, "text" to it.text, "vector" to JSONArray(it.vector))
            }),
            "keypoints" to JSONArray(input.keypoints.map {
                json("keypoint_id" to it.id, "vector" to JSONArray(it.vector))
            })))
    }

    fun output(module: Module, data: JSONObject): ModuleOutput = when (module) {
        Module.M1 -> Segments(data.getJSONArray("segments").read {
            Segment(it.getString("segment_id"), it.getInt("start_sample"), it.getInt("end_sample"),
                Base64.getDecoder().decode(it.getString("pcm_b64")))
        })
        Module.M2 -> readTranscript(data.getJSONObject("transcript"))
        Module.M3 -> data.getJSONObject("embeddings").let { value ->
            Embeddings(value.getInt("dimension"),
                value.getJSONArray("answer_sentences").read {
                    SentenceVector(it.getString("sentence_id"), it.getString("text"), vector(it))
                },
                value.getJSONArray("keypoints").read {
                    KeypointVector(it.getString("keypoint_id"), vector(it))
                })
        }
        Module.M4 -> readMatches(data.getJSONArray("matches"))
        else -> throw ModuleFailure(ErrorCode.UNKNOWN_MODULE)
    }

    private fun base64(pcm: ByteArray): String = Base64.getEncoder().encodeToString(pcm)

    private fun vector(item: JSONObject): List<Double> = item.getJSONArray("vector").let { array ->
        (0 until array.length()).map { array.getDouble(it).also { value -> require(value.isFinite()) } }
    }

    fun transcript(value: Transcript): JSONObject = json("full_text" to value.fullText,
        "segments" to JSONArray(value.segments.map {
            json("segment_id" to it.id, "start_sample" to it.start, "end_sample" to it.end, "text" to it.text)
        }))

    fun readTranscript(data: JSONObject): Transcript = Transcript(
        data.getString("full_text"), data.getJSONArray("segments").read {
            TranscriptSegment(it.getString("segment_id"), it.getInt("start_sample"), it.getInt("end_sample"),
                it.getString("text"))
        })

    fun matches(value: Matches): JSONArray = JSONArray(value.values.map {
        json("keypoint_id" to it.keypointId, "score" to it.score, "covered" to it.covered,
            "evidence_sentence_id" to it.evidenceId, "evidence_text" to it.evidenceText)
    })

    fun readMatches(data: JSONArray): Matches = Matches(data.read {
        val score = it.getDouble("score")
        require(score in -1.0..1.0)
        Match(it.getString("keypoint_id"), score, it.getBoolean("covered"),
            it.getString("evidence_sentence_id"), it.getString("evidence_text"))
    })

    fun plan(value: ExecutionPlan): JSONObject = json("schema_version" to 1,
        "plan_version" to value.planVersion, "device_id" to value.deviceId, "model_version" to value.modelVersion,
        "config_version" to value.configVersion, "mode" to value.mode.name, "cost_table_version" to null,
        "assignments" to JSONObject(value.assignments.mapKeys { it.key.name }.mapValues { it.value.name }))

    fun readPlan(data: JSONObject): ExecutionPlan = ExecutionPlan(
        data.getString("plan_version"), data.getString("device_id"), data.getString("model_version"),
        data.getString("config_version"), PlanMode.valueOf(data.getString("mode")),
        Module.values().filter { data.getJSONObject("assignments").getString(it.name) == "REMOTE" }.toSet())
}
