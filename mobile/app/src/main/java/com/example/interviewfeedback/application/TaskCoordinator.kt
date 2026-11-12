package com.example.interviewfeedback.application

import java.util.UUID

enum class TaskStatus { CREATED, RUNNING, SUCCEEDED, FAILED, CANCELLED, INTERRUPTED }
enum class InputSource { RECORDING, IMPORT }

data class TaskRecord(
    val taskId: String, val plan: ExecutionPlan, val source: InputSource,
    val runId: String, val sampleId: String, val submittedAtMs: Long,
    val status: TaskStatus = TaskStatus.CREATED, val attempt: Int = 1,
    val feedback: Feedback? = null, val error: ErrorCode? = null,
    val visible: Boolean = false, val effectiveInput: Boolean? = null,
    val audioSamples: Int? = null,
    val measurements: List<ModuleMeasurement> = emptyList(),
    val totalElapsedMs: Long? = null, val feedbackElapsedMs: Long? = null,
    val experiment: ExperimentLink? = null,
)

interface TaskJournal {
    /** Replace one task atomically, including terminal state and adopted result. */
    fun save(record: TaskRecord)
    fun unfinished(): List<TaskRecord>
}

data class TaskEvent(
    val task: TaskRecord, val event: String, val status: String,
    val module: Module? = null, val executor: Executor? = null,
    val timing: Timing? = null, val error: ErrorCode? = null,
)

fun interface EventSink { fun append(event: TaskEvent) }

class TaskCoordinator(
    private val local: ModuleExecutor,
    private val remote: ModuleExecutor,
    private val journal: TaskJournal,
    private val events: EventSink,
) {
    private var current: TaskRecord? = null
    private var workerTask: String? = null

    init {
        journal.unfinished().forEach {
            val recovered = it.copy(status = TaskStatus.INTERRUPTED)
            journal.save(recovered)
            publish(TaskEvent(recovered, "TASK_TERMINAL", recovered.status.name))
        }
    }

    @Synchronized
    fun current(): TaskRecord? = current

    /** Call at stop/submit. effectiveInput describes the preclassified experiment sample. */
    @Synchronized
    fun begin(
        plan: ExecutionPlan, source: InputSource, runId: String, sampleId: String,
        effectiveInput: Boolean? = null,
        submittedAtNanos: Long = System.nanoTime(),
        experiment: ExperimentLink? = null,
    ): TaskRecord {
        check(workerTask == null && current?.status !in setOf(TaskStatus.CREATED, TaskStatus.RUNNING))
        val record = TaskRecord(UUID.randomUUID().toString(), plan, source, runId, sampleId,
            submittedAtNanos / 1_000_000L, effectiveInput = effectiveInput, experiment = experiment)
        journal.save(record)
        current = record
        publish(TaskEvent(record, "TASK_SUBMITTED", record.status.name))
        return record
    }

    /** Run on a background executor. prepareAudio and local/remote adapters never touch UI. */
    fun run(taskId: String, keypoints: List<Keypoint>, budgetMs: Int,
            priorAudioPreparationMs: Long = 0, prepareAudio: () -> Audio) {
        require(budgetMs > 0 && priorAudioPreparationMs >= 0)
        val active = synchronized(this) {
            val record = current
            if (record?.taskId != taskId || record.status != TaskStatus.CREATED || workerTask != null) return
            val running = record.copy(status = TaskStatus.RUNNING)
            journal.save(running)
            current = running
            workerTask = taskId
            running
        }
        val deadline = active.submittedAtMs + budgetMs
        try {
            val started = nowMs()
            val audio = try {
                if (started >= deadline) throw ModuleFailure(ErrorCode.DEADLINE_EXCEEDED)
                prepareAudio().also {
                    if (it.sampleCount !in 1..960000 || it.pcm.size != it.sampleCount * 2)
                        throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
                }
            } catch (failure: Exception) {
                val code = (failure as? ModuleFailure)?.code ?: ErrorCode.INTERNAL_ERROR
                synchronized(this) {
                    if (isActive(active)) {
                        publish(TaskEvent(active, "MODULE_END", "ERROR", Module.M0,
                            Executor.LOCAL, Timing(nowMs() - started + priorAudioPreparationMs), code))
                    }
                }
                throw ModuleFailure(code)
            }
            synchronized(this) {
                if (!isActive(active)) return
                val captured = active.copy(audioSamples = audio.sampleCount)
                journal.save(captured)
                current = captured
                publish(TaskEvent(captured, "MODULE_END", "OK", Module.M0, Executor.LOCAL,
                    Timing(nowMs() - started + priorAudioPreparationMs)))
            }
            val segments = step(active, Module.M1, audio, deadline) as Segments
            val transcript = step(active, Module.M2, segments, deadline) as Transcript
            val embeddings = step(active, Module.M3, EncodeInput(transcript, keypoints.toList()), deadline) as Embeddings
            val matches = step(active, Module.M4, embeddings, deadline) as Matches
            synchronized(this) {
                if (!isActive(active)) return
                if (nowMs() >= deadline) throw ModuleFailure(ErrorCode.DEADLINE_EXCEEDED)
                val saveStarted = nowMs()
                val success = checkNotNull(current).copy(
                    status = TaskStatus.SUCCEEDED, feedback = Feedback(transcript, matches),
                )
                journal.save(success)
                current = success
                publish(TaskEvent(success, "MODULE_END", "OK", Module.M5, Executor.LOCAL,
                    Timing(nowMs() - saveStarted)))
                terminalEvent(success)
            }
        } catch (_: TaskStopped) {
            // Cancellation already persisted the terminal state.
        } catch (failure: Exception) {
            synchronized(this) {
                if (isActive(active)) {
                    finish(checkNotNull(current), TaskStatus.FAILED,
                        (failure as? ModuleFailure)?.code ?: ErrorCode.INTERNAL_ERROR)
                }
            }
        } finally {
            synchronized(this) { if (workerTask == taskId) workerTask = null }
        }
    }

    @Synchronized
    fun cancel(taskId: String): Boolean {
        val record = current ?: return false
        if (record.taskId != taskId || record.status !in setOf(TaskStatus.CREATED, TaskStatus.RUNNING)) return false
        finish(record, TaskStatus.CANCELLED, null)
        return true
    }

    /** Call after the UI has drawn the full feedback for this task and attempt. */
    @Synchronized
    fun markFeedbackVisible(taskId: String, attempt: Int, visibleAtNanos: Long = System.nanoTime()): Boolean {
        val record = current ?: return false
        if (record.taskId != taskId || record.attempt != attempt ||
            record.status != TaskStatus.SUCCEEDED || record.visible) return false
        val visible = record.copy(visible = true)
        journal.save(visible)
        current = visible
        publish(TaskEvent(visible, "FEEDBACK_VISIBLE", "OK",
            timing = Timing((visibleAtNanos / 1_000_000L - visible.submittedAtMs).coerceAtLeast(0))))
        return true
    }

    private fun isActive(record: TaskRecord): Boolean =
        current?.taskId == record.taskId && current?.attempt == record.attempt && current?.status == TaskStatus.RUNNING

    private fun step(active: TaskRecord, module: Module, input: ModuleInput, deadline: Long): ModuleOutput {
        synchronized(this) { if (!isActive(active)) throw TaskStopped() }
        val plan = active.plan
        val remaining = deadline - nowMs()
        val id = CallId(active.taskId, active.attempt, module, plan.planVersion, plan.modelVersion, plan.configVersion)
        val side = plan.executor(module)
        val started = nowMs()
        val result = if (remaining <= 0) {
            ModuleResult.Error(id, side, Timing(0, moduleTimeKnown = false), ErrorCode.DEADLINE_EXCEEDED)
        } else {
            val adapter = if (side == Executor.LOCAL) local else remote
            try {
                adapter.execute(ModuleRequest(id, remaining.toInt(), input))
            } catch (_: Exception) {
                ModuleResult.Error(id, side, Timing(nowMs() - started, moduleTimeKnown = false), ErrorCode.INTERNAL_ERROR)
            }
        }
        synchronized(this) {
            val record = checkNotNull(current)
            val sameId = result.id == id && result.executor == side
            if (!isActive(active) || !sameId) {
                publish(TaskEvent(record, "MODULE_END", "IGNORED", module, side, result.timing,
                    if (sameId) null else ErrorCode.VERSION_MISMATCH))
                if (!isActive(active)) throw TaskStopped()
                throw ModuleFailure(ErrorCode.VERSION_MISMATCH)
            }
            val code = when {
                result is ModuleResult.Error -> result.code
                nowMs() >= deadline -> ErrorCode.DEADLINE_EXCEEDED
                else -> null
            }
            publish(TaskEvent(record, "MODULE_END", if (code == null) "OK" else "ERROR",
                module, side, result.timing, code))
            if (code != null) throw ModuleFailure(code)
            return (result as ModuleResult.Ok).output
        }
    }

    private fun finish(record: TaskRecord, status: TaskStatus, code: ErrorCode?) {
        val terminal = record.copy(status = status, error = code)
        journal.save(terminal)
        current = terminal
        terminalEvent(terminal)
    }

    private fun terminalEvent(record: TaskRecord) {
        publish(TaskEvent(record, "TASK_TERMINAL", record.status.name,
            timing = Timing(nowMs() - record.submittedAtMs), error = record.error))
    }

    /** Persist the same timings that are sent to the UI and exported as events. */
    private fun publish(event: TaskEvent) {
        val active = current
        if (active?.taskId != event.task.taskId || active.attempt != event.task.attempt) {
            events.append(event)
            return
        }
        val updated = when {
            event.event == "MODULE_END" && event.status != "IGNORED" && event.module != null && event.timing != null ->
                active.copy(measurements = active.measurements.filterNot { it.module == event.module } +
                    ModuleMeasurement(event.module, checkNotNull(event.executor), event.status, event.timing, event.error))
            event.event == "TASK_TERMINAL" -> active.copy(totalElapsedMs = event.timing?.elapsedMs)
            event.event == "FEEDBACK_VISIBLE" -> active.copy(feedbackElapsedMs = event.timing?.elapsedMs)
            else -> active
        }
        if (updated !== active) { journal.save(updated); current = updated }
        events.append(event.copy(task = updated))
    }

    private class TaskStopped : Exception()
}
