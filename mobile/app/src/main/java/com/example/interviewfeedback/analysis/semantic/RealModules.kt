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
    private val negatedAction = Regex("不打算|不准备|无需|不用|不做|不考虑|不安排|不需要|不会(?:做|再|去|提供|回访|调整|记录|设置|组织|提醒)")
    private fun artifact(key: String) = File(directory, artifacts.getJSONObject(key).getString("path"))
    private val vadResource = lazy { session("vad") }
    private val semanticResource = lazy { session("semantic") }
    private val tokenizerResource = lazy { SentencePiece(artifact("tokenizer").path) }
    private val asrResource = lazy { Model(File(directory, manifest.getString("vosk_directory")).path) }
    private val vadSession get() = vadResource.value
    private val semanticSession get() = semanticResource.value
    private val tokenizer get() = tokenizerResource.value
    private val asrModel get() = asrResource.value

    private fun session(key: String): OrtSession = OrtSession.SessionOptions().use {
        environment.createSession(artifact(key).path, it).also { sessions.add(it) }
    }

    companion object {
        /** 取依据时的分数容差带：只在该范围内挑句子，避免把明显更差的句子当依据。 */
        const val EVIDENCE_BAND = 0.85

        /** 依据句与要点原文的最小连续重合字数，低于此值视为没有更好的依据，退回最高分句。 */
        const val EVIDENCE_MIN_OVERLAP = 2

        fun verifyArtifacts(directory: File, manifest: JSONObject) {
        val artifacts = manifest.getJSONObject("artifacts")
        for (key in artifacts.keys()) {
            val descriptor = artifacts.getJSONObject(key)
            val file = File(directory, descriptor.getString("path")).canonicalFile
            require(file.toPath().startsWith(directory.canonicalFile.toPath()))
            val hash = java.security.MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) { val count = input.read(buffer); if (count < 0) break; hash.update(buffer, 0, count) }
            }
            require(hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) } == descriptor.getString("sha256"))
        }
        }
    }

    init {
        verifyArtifacts(directory, manifest)
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
                }
            } finally { inputs.values.forEach { it.close() } }
        }
        val norm = sqrt(sum.sumOf { it * it })
        if (!norm.isFinite() || norm == 0.0) throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        return sum.map { it / norm }
    }

    override fun encode(input: EncodeInput, id: CallId): Embeddings {
        val starts = Regex("然后|接下来|之后|结束后|活动结束|同时|现场|不过|但是|但我|但不|也不|不会|不做|再和|再去|再请|最后|每天|每周")
        val clauses = Regex("[^。！？!?；;\n]+[。！？!?；;]?").findAll(input.transcript.fullText)
            .flatMap { match ->
                val text = match.value.trim()
                val offsets = listOf(0) + starts.findAll(text).map { it.range.first }.filter { it > 0 }.toList()
                (offsets + text.length).zipWithNext().map { (left, right) -> text.substring(left, right).trim() }
                    .filter { it.length >= 5 }
            }.toList().ifEmpty { listOf(input.transcript.fullText.trim()).filter { it.isNotEmpty() } }
        val sentences = clauses.flatMap { clause ->
            listOf(clause) + if (clause.length > 28 && !negatedAction.containsMatchIn(clause))
                clause.indices.step(14).map { start -> clause.substring(start, minOf(start + 28, clause.length)) }
                    .filter { it.length >= 8 }
            else emptyList()
        }.distinct()
        if (sentences.isEmpty()) throw ModuleFailure(ErrorCode.NO_TRANSCRIPT)
        return Embeddings(dimension, sentences.mapIndexed { index, text ->
            SentenceVector("s${index + 1}", text, vector(text))
        }, input.keypoints.map { KeypointVector(it.id, it.text, vector(it.text)) })
    }

    /** 最长公共子串长度，用来在分数相近的候选里挑真正贴切的依据句。 */
    private fun overlap(left: String, right: String): Int {
        if (left.isEmpty() || right.isEmpty()) return 0
        var previous = IntArray(right.length + 1)
        var best = 0
        for (index in 1..left.length) {
            val current = IntArray(right.length + 1)
            val char = left[index - 1]
            for (other in 1..right.length) if (char == right[other - 1]) {
                current[other] = previous[other - 1] + 1
                if (current[other] > best) best = current[other]
            }
            previous = current
        }
        return best
    }

    override fun match(embeddings: Embeddings, id: CallId): Matches {
        if (embeddings.dimension != dimension || embeddings.sentences.isEmpty()) throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        val all = embeddings.sentences.map { it.vector } + embeddings.keypoints.map { it.vector }
        if (all.any { values -> values.size != dimension || values.any { !it.isFinite() } ||
                kotlin.math.abs(sqrt(values.sumOf { it * it }) - 1) > 1e-5 })
            throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        val eligible = embeddings.sentences.indices.filter { index ->
            !negatedAction.containsMatchIn(embeddings.sentences[index].text)
        }
        val threshold = config.getDouble("match_threshold")
        return Matches(embeddings.keypoints.map { key ->
            val scores = embeddings.sentences.map { sentence -> key.vector.zip(sentence.vector).sumOf { it.first * it.second } }
            val pool = eligible.ifEmpty { scores.indices.toList() }
            val best = pool.maxBy { scores[it] }
            val score = scores[best].coerceIn(-1.0, 1.0)
            // 短句在余弦空间里天然占优：句中概念越少，单个概念在归一化向量里的权重越高，
            // 于是短句常以微弱优势压过长句。分数与覆盖判定仍用最高分句，只把“依据”换成
            // 分数相近、且与要点原文重合更长的句子；找不到合格候选就退回最高分句。
            val band = pool.filter { scores[it] >= scores[best] * EVIDENCE_BAND }
            val evidence = band.map { it to overlap(embeddings.sentences[it].text, key.text) }
                .filter { (_, shared) -> shared >= EVIDENCE_MIN_OVERLAP }
                .maxWithOrNull(compareBy<Pair<Int, Int>> { it.second }.thenBy { scores[it.first] })
                ?.first ?: best
            val sentence = embeddings.sentences[evidence]
            Match(key.id, score, eligible.isNotEmpty() && score >= threshold, sentence.id, sentence.text)
        })
    }

    override fun close() {
        if (asrResource.isInitialized()) asrResource.value.close()
        if (tokenizerResource.isInitialized()) tokenizerResource.value.close()
        sessions.forEach { it.close() }
    }
}
