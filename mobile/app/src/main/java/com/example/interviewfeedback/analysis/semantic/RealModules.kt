package com.example.interviewfeedback.analysis.semantic

import ai.onnxruntime.*
import com.example.interviewfeedback.application.*
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.LongBuffer
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import kotlin.math.sqrt

/** Owned by the app background executor; release after all calls finish. */
class RealModules(private val directory: File) : LocalModules, AutoCloseable {
    private val manifest = JSONObject(File(directory, "manifest.json").readText())
    private val config = manifest.getJSONObject("config")
    private val artifacts = manifest.getJSONObject("artifacts")
    private val environment = OrtEnvironment.getEnvironment()
    private val sessions = mutableListOf<OrtSession>()
    private val dimension = config.getInt("dimension")
    private val maxLength = config.getInt("max_length")
    private fun artifact(key: String) = File(directory, artifacts.getJSONObject(key).getString("path"))
    private val vadSession: OrtSession
    private val semanticSession: OrtSession
    private val tokenizer: SentencePiece
    private val asrModel: Model

    init {
        for (key in artifacts.keys()) {
            val descriptor = artifacts.getJSONObject(key)
            val file = artifact(key).canonicalFile
            require(file.toPath().startsWith(directory.canonicalFile.toPath()))
            val hash = java.security.MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) { val count = input.read(buffer); if (count < 0) break; hash.update(buffer, 0, count) }
            }
            require(hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) } == descriptor.getString("sha256"))
        }
        try {
            vadSession = environment.createSession(artifact("vad").path, OrtSession.SessionOptions()).also { sessions.add(it) }
            semanticSession = environment.createSession(artifact("semantic").path, OrtSession.SessionOptions()).also { sessions.add(it) }
            tokenizer = SentencePiece(artifact("tokenizer").path)
            asrModel = Model(File(directory, manifest.getString("vosk_directory")).path)
        } catch (error: Exception) {
            sessions.forEach { it.close() }
            throw error
        }
    }

    override fun vad(audio: Audio, id: CallId): Segments {
        if (audio.sampleCount !in 1..960000 || audio.pcm.size != audio.sampleCount * 2)
            throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        val samples = ByteBuffer.wrap(audio.pcm).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        var state = FloatArray(256)
        var context = FloatArray(64)
        var start: Int? = null
        var silence = 0
        val intervals = mutableListOf<Pair<Int, Int>>()
        for (offset in 0 until audio.sampleCount step 512) {
            val frame = FloatArray(512) { index ->
                if (offset + index < audio.sampleCount) samples.get(offset + index) / 32768f else 0f
            }
            val input = context + frame
            OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), longArrayOf(1, 576)).use { waveform ->
                OnnxTensor.createTensor(environment, FloatBuffer.wrap(state), longArrayOf(2, 1, 128)).use { memory ->
                    OnnxTensor.createTensor(environment, LongBuffer.wrap(longArrayOf(16000)), longArrayOf()).use { rate ->
                        vadSession.run(mapOf("input" to waveform, "state" to memory, "sr" to rate)).use { output ->
                            val probability = (output[0] as OnnxTensor).floatBuffer.get(0)
                            state = FloatArray(256).also { (output[1] as OnnxTensor).floatBuffer.get(it) }
                            if (probability >= config.getDouble("vad_threshold")) {
                                if (start == null) start = maxOf(0, offset - 480)
                                silence = 0
                            } else if (start != null) {
                                silence++
                                if (silence >= 10) {
                                    intervals.add(checkNotNull(start) to minOf(audio.sampleCount, offset - 9 * 512 + 480))
                                    start = null
                                    silence = 0
                                }
                            }
                        }
                    }
                }
            }
            context = frame.copyOfRange(448, 512)
        }
        start?.let { intervals.add(it to audio.sampleCount) }
        val merged = mutableListOf<Pair<Int, Int>>()
        for ((left, right) in intervals) {
            if (merged.isNotEmpty() && left <= merged.last().second) {
                merged[merged.lastIndex] = merged.last().first to maxOf(right, merged.last().second)
            } else merged.add(left to right)
        }
        if (merged.isEmpty()) throw ModuleFailure(ErrorCode.NO_SPEECH)
        return Segments(merged.mapIndexed { index, (left, right) ->
            Segment("seg${index + 1}", left, right, audio.pcm.copyOfRange(left * 2, right * 2))
        })
    }

    override fun asr(segments: Segments, id: CallId): Transcript {
        val output = segments.values.map { segment ->
            Recognizer(asrModel, 16000f).use { recognizer ->
                val text = StringBuilder()
                var offset = 0
                while (offset < segment.pcm.size) {
                    val end = minOf(segment.pcm.size, offset + 8000)
                    val bytes = segment.pcm.copyOfRange(offset, end)
                    if (recognizer.acceptWaveForm(bytes, bytes.size)) text.append(JSONObject(recognizer.result).optString("text"))
                    offset = end
                }
                text.append(JSONObject(recognizer.finalResult).optString("text"))
                TranscriptSegment(segment.id, segment.start, segment.end, text.toString().replace(" ", "").trim())
            }
        }
        val full = output.map { it.text }.filter { it.isNotEmpty() }.joinToString("\n")
        if (full.isEmpty()) throw ModuleFailure(ErrorCode.NO_TRANSCRIPT)
        return Transcript(full, output)
    }

    private fun vector(text: String): List<Double> {
        val pieces = tokenizer.encode(text).map { if (it == 0) 3 else it + 1 }
        val blocks = if (pieces.isEmpty()) listOf(emptyList()) else pieces.chunked(maxLength - 2)
        val sum = DoubleArray(dimension)
        var totalWeight = 0
        for (block in blocks) {
            val ids = (listOf(0) + block + listOf(2)).map { it.toLong() }.toLongArray()
            val inputs = mutableMapOf<String, OnnxTensor>()
            try {
                for (name in semanticSession.inputNames) {
                    val values = when (name) {
                        "input_ids" -> ids
                        "attention_mask" -> LongArray(ids.size) { 1 }
                        "token_type_ids" -> LongArray(ids.size)
                        else -> throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
                    }
                    inputs[name] = OnnxTensor.createTensor(environment, LongBuffer.wrap(values), longArrayOf(1, ids.size.toLong()))
                }
                semanticSession.run(inputs).use { outputs ->
                    val tensor = outputs[0] as OnnxTensor
                    val values = tensor.floatBuffer
                    val tokenCount = if (tensor.info.shape.size == 3) ids.size else 1
                    val weight = maxOf(1, block.size)
                    for (column in 0 until dimension) {
                        var pooled = 0.0
                        for (row in 0 until tokenCount) pooled += values.get(row * dimension + column)
                        sum[column] += pooled / tokenCount * weight
                    }
                    totalWeight += weight
                }
            } finally { inputs.values.forEach { it.close() } }
        }
        val norm = sqrt(sum.sumOf { it * it })
        if (!norm.isFinite() || norm == 0.0) throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        return sum.map { it / norm }
    }

    override fun encode(input: EncodeInput, id: CallId): Embeddings {
        val sentences = Regex("[^。！？!?；;\n]+[。！？!?；;]?").findAll(input.transcript.fullText)
            .map { it.value.trim() }.filter { it.isNotEmpty() }.toList()
        if (sentences.isEmpty()) throw ModuleFailure(ErrorCode.NO_TRANSCRIPT)
        return Embeddings(dimension, sentences.mapIndexed { index, text ->
            SentenceVector("s${index + 1}", text, vector(text))
        }, input.keypoints.map { KeypointVector(it.id, vector(it.text)) })
    }

    override fun match(embeddings: Embeddings, id: CallId): Matches {
        if (embeddings.dimension != dimension || embeddings.sentences.isEmpty()) throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        val all = embeddings.sentences.map { it.vector } + embeddings.keypoints.map { it.vector }
        if (all.any { values -> values.size != dimension || values.any { !it.isFinite() } ||
                kotlin.math.abs(sqrt(values.sumOf { it * it }) - 1) > 1e-5 })
            throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        return Matches(embeddings.keypoints.map { key ->
            val scores = embeddings.sentences.map { sentence -> key.vector.zip(sentence.vector).sumOf { it.first * it.second } }
            val best = scores.indices.maxBy { scores[it] }
            val sentence = embeddings.sentences[best]
            val score = scores[best].coerceIn(-1.0, 1.0)
            Match(key.id, score, score >= config.getDouble("match_threshold"), sentence.id, sentence.text)
        })
    }

    override fun close() { asrModel.close(); tokenizer.close(); sessions.forEach { it.close() } }
}
