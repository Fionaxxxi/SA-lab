package com.example.interviewfeedback.application

import java.util.Collections

enum class Module { M0, M1, M2, M3, M4, M5 }
enum class Executor { LOCAL, REMOTE }
enum class PlanMode { LOCAL, REMOTE, MANUAL_MIXED }

class ExecutionPlan(
    val planVersion: String,
    val deviceId: String,
    val modelVersion: String,
    val configVersion: String,
    val mode: PlanMode,
    remote: Set<Module> = emptySet(),
) {
    val assignments: Map<Module, Executor>

    init {
        val eligible = setOf(Module.M1, Module.M2, Module.M3, Module.M4)
        require(eligible.containsAll(remote))
        require(when (mode) {
            PlanMode.LOCAL -> remote.isEmpty()
            PlanMode.REMOTE -> remote == eligible
            PlanMode.MANUAL_MIXED -> remote.isNotEmpty() && remote != eligible
        })
        val identity = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        require(listOf(planVersion, deviceId, modelVersion, configVersion).all(identity::matches))
        assignments = Collections.unmodifiableMap(Module.values().associateWith {
            if (it in remote) Executor.REMOTE else Executor.LOCAL
        })
    }

    fun executor(module: Module): Executor = assignments.getValue(module)
}

sealed interface ModuleInput
sealed interface ModuleOutput

data class Audio(val sampleCount: Int, val pcm: ByteArray) : ModuleInput
data class Segment(val id: String, val start: Int, val end: Int, val pcm: ByteArray)
data class Segments(val values: List<Segment>) : ModuleInput, ModuleOutput
data class TranscriptSegment(val id: String, val start: Int, val end: Int, val text: String)
data class Transcript(val fullText: String, val segments: List<TranscriptSegment>) : ModuleOutput
data class Keypoint(val id: String, val text: String)
data class EncodeInput(val transcript: Transcript, val keypoints: List<Keypoint>) : ModuleInput
data class SentenceVector(val id: String, val text: String, val vector: List<Double>)
data class KeypointVector(val id: String, val vector: List<Double>)
data class Embeddings(
    val dimension: Int,
    val sentences: List<SentenceVector>,
    val keypoints: List<KeypointVector>,
) : ModuleInput, ModuleOutput
data class Match(
    val keypointId: String, val score: Double, val covered: Boolean,
    val evidenceId: String, val evidenceText: String,
)
data class Matches(val values: List<Match>) : ModuleOutput
data class Feedback(val transcript: Transcript, val matches: Matches)

data class CallId(
    val taskId: String, val attempt: Int, val module: Module, val planVersion: String,
    val modelVersion: String, val configVersion: String, val schemaVersion: Int = 1,
)

data class ModuleRequest(val id: CallId, val remainingBudgetMs: Int, val payload: ModuleInput)
data class Timing(
    val elapsedMs: Long,
    val bytesUp: Long = 0,
    val bytesDown: Long = 0,
    val roundTripMs: Long? = null,
    val encodeMs: Long? = null,
    val decodeMs: Long? = null,
    val moduleTimeKnown: Boolean = true,
)

enum class ErrorCode {
    INVALID_PAYLOAD, VERSION_MISMATCH, IN_PROGRESS, REQUEST_CONFLICT, PAYLOAD_TOO_LARGE,
    UNAUTHORIZED, UNKNOWN_MODULE, NO_SPEECH, NO_TRANSCRIPT, MODEL_UNAVAILABLE, BUSY,
    DEADLINE_EXCEEDED, REMOTE_UNREACHABLE, INTERNAL_ERROR,
}

class ModuleFailure(val code: ErrorCode) : Exception(code.name)

sealed interface ModuleResult {
    val id: CallId
    val executor: Executor
    val timing: Timing

    data class Ok(
        override val id: CallId, override val executor: Executor, override val timing: Timing,
        val output: ModuleOutput,
    ) : ModuleResult

    data class Error(
        override val id: CallId, override val executor: Executor, override val timing: Timing,
        val code: ErrorCode,
    ) : ModuleResult
}

fun interface ModuleExecutor {
    fun execute(request: ModuleRequest): ModuleResult
}

/** Liu and Peng provide the four local functions; the coordinator owns routing. */
interface LocalModules {
    fun vad(audio: Audio, id: CallId): Segments
    fun asr(segments: Segments, id: CallId): Transcript
    fun encode(input: EncodeInput, id: CallId): Embeddings
    fun match(embeddings: Embeddings, id: CallId): Matches
}

internal fun nowMs(): Long = System.nanoTime() / 1_000_000L

class LocalExecutor(private val modules: LocalModules) : ModuleExecutor {
    override fun execute(request: ModuleRequest): ModuleResult {
        val started = nowMs()
        val id = request.id
        return try {
            val output = when (id.module) {
                Module.M1 -> modules.vad(request.payload as Audio, id)
                Module.M2 -> modules.asr(request.payload as Segments, id)
                Module.M3 -> modules.encode(request.payload as EncodeInput, id)
                Module.M4 -> modules.match(request.payload as Embeddings, id)
                else -> throw ModuleFailure(ErrorCode.UNKNOWN_MODULE)
            }
            val duration = nowMs() - started
            if (duration >= request.remainingBudgetMs) throw ModuleFailure(ErrorCode.DEADLINE_EXCEEDED)
            ModuleResult.Ok(id, Executor.LOCAL, Timing(duration), output)
        } catch (error: ModuleFailure) {
            ModuleResult.Error(id, Executor.LOCAL, Timing(nowMs() - started), error.code)
        }
    }
}
