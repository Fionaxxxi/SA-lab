package com.example.interviewfeedback.application

import com.example.interviewfeedback.transport.FileTaskJournal
import com.example.interviewfeedback.transport.JsonlEventSink
import com.example.interviewfeedback.transport.RemoteExecutor
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import okhttp3.HttpUrl.Companion.toHttpUrl

private const val TEXT = "先调查居民需求"
private val KEYPOINTS = listOf(Keypoint("k1", TEXT))
private val AUDIO = Audio(2, byteArrayOf(1, 2, 3, 4))
private val REMOTE_MODULES = setOf(Module.M1, Module.M2, Module.M3, Module.M4)

private class Fixtures : LocalModules {
    override fun vad(audio: Audio, id: CallId) =
        Segments(listOf(Segment("seg1", 0, audio.sampleCount, audio.pcm)))

    override fun asr(segments: Segments, id: CallId) =
        Transcript(TEXT, segments.values.map { TranscriptSegment(it.id, it.start, it.end, TEXT) })

    override fun encode(input: EncodeInput, id: CallId) = Embeddings(
        2, listOf(SentenceVector("s1", TEXT, listOf(1.0, 0.0))),
        input.keypoints.map { KeypointVector(it.id, it.text, listOf(1.0, 0.0)) })

    override fun match(embeddings: Embeddings, id: CallId) =
        Matches(embeddings.keypoints.map { Match(it.id, 1.0, true, "s1", TEXT) })
}

private fun plan(mode: PlanMode, nodes: Set<Module> = emptySet()) = ExecutionPlan(
    "plan-${mode.name}", "jvm-fixture", "modelset-demo", "rules-demo", mode, nodes)

fun main(args: Array<String>) {
    require(args.size == 2)
    val directory = File(args[1]).apply { mkdirs() }
    val sink = JsonlEventSink(File(directory, "coordinator.jsonl"))
    val events = mutableListOf<TaskEvent>()
    val capture = EventSink { events.add(it); sink.append(it) }
    val journal = FileTaskJournal(File(directory, "tasks"))
    val local = LocalExecutor(Fixtures())
    val remote = RemoteExecutor(args[0].toHttpUrl(), "fixture-token")
    val coordinator = TaskCoordinator(local, remote, journal, capture)
    val mixedNodes = mutableSetOf(Module.M2, Module.M3)
    val mixed = plan(PlanMode.MANUAL_MIXED, mixedNodes)
    mixedNodes.clear()
    val plans = listOf(plan(PlanMode.LOCAL), plan(PlanMode.REMOTE, REMOTE_MODULES), mixed)
    var previousTask: TaskRecord? = null
    for (configuration in plans) {
        val task = coordinator.begin(configuration, InputSource.IMPORT, "demo-${configuration.mode.name.lowercase()}", "synthetic-pcm", true)
        previousTask?.let { check(!coordinator.markFeedbackVisible(it.taskId, it.attempt)) }
        coordinator.run(task.taskId, KEYPOINTS, 5000) { AUDIO }
        val result = checkNotNull(coordinator.current())
        check(result.status == TaskStatus.SUCCEEDED) { result.toString() }
        check(result.feedback == Feedback(
            Transcript(TEXT, listOf(TranscriptSegment("seg1", 0, 2, TEXT))),
            Matches(listOf(Match("k1", 1.0, true, "s1", TEXT)))))
        check(journal.load(task.taskId)?.status == TaskStatus.SUCCEEDED)
        check(journal.load(task.taskId)?.feedback == result.feedback)
        check(coordinator.markFeedbackVisible(task.taskId, task.attempt))
        check(!coordinator.markFeedbackVisible(task.taskId, task.attempt))
        val modules = events.filter { it.task.taskId == task.taskId && it.event == "MODULE_END" }
        check(modules.map { it.module } == Module.values().toList())
        for (event in modules) {
            val expected = configuration.executor(checkNotNull(event.module))
            check(event.executor == expected)
            val timing = checkNotNull(event.timing)
            if (expected == Executor.REMOTE) {
                check(timing.bytesUp > 0 && timing.bytesDown > 0 && timing.roundTripMs != null)
            } else {
                check(timing.bytesUp == 0L && timing.bytesDown == 0L && timing.roundTripMs == null)
            }
        }
        println("${configuration.mode} OK ${modules.joinToString { "${it.module}=${it.executor}" }}")
        previousTask = task
    }

    val started = CountDownLatch(1)
    val release = CountDownLatch(1)
    val blocked = ModuleExecutor { request ->
        started.countDown()
        check(release.await(3, TimeUnit.SECONDS))
        local.execute(request)
    }
    val cancellation = TaskCoordinator(blocked, remote, journal, capture)
    val task = cancellation.begin(plans[0], InputSource.RECORDING, "demo-fault-recording", "cancel")
    val worker = thread { cancellation.run(task.taskId, KEYPOINTS, 5000) { AUDIO } }
    try {
        check(started.await(3, TimeUnit.SECONDS))
        check(cancellation.cancel(task.taskId))
        check(journal.load(task.taskId)?.status == TaskStatus.CANCELLED)
    } finally {
        release.countDown()
        worker.join()
    }
    check(journal.load(task.taskId)?.feedback == null)
    check(events.any { it.task.taskId == task.taskId && it.status == "IGNORED" })
    println("CANCELLED ignores late output OK")

    val stale = ModuleExecutor { request ->
        val actual = local.execute(request) as ModuleResult.Ok
        actual.copy(id = actual.id.copy(attempt = 2))
    }
    val guarded = TaskCoordinator(stale, remote, journal, capture)
    val guardedTask = guarded.begin(plans[0], InputSource.IMPORT, "demo-fault-import", "stale")
    guarded.run(guardedTask.taskId, KEYPOINTS, 5000) { AUDIO }
    check(journal.load(guardedTask.taskId)?.error == ErrorCode.VERSION_MISMATCH)
    check(journal.load(guardedTask.taskId)?.feedback == null)
    println("OLD ATTEMPT rejected OK")

    val failed = coordinator.begin(plans[0], InputSource.IMPORT, "demo-fault-import", "invalid", false)
    coordinator.run(failed.taskId, KEYPOINTS, 5000) { Audio(5, ByteArray(1)) }
    check(journal.load(failed.taskId)?.error == ErrorCode.INVALID_PAYLOAD)
    println("INVALID PCM failed with event OK")

    val pending = coordinator.begin(plans[0], InputSource.IMPORT, "demo-fault-import", "interrupted")
    val recovered = TaskCoordinator(local, remote, FileTaskJournal(File(directory, "tasks")), capture)
    check(journal.load(pending.taskId)?.status == TaskStatus.INTERRUPTED)
    recovered.run(pending.taskId, KEYPOINTS, 5000) { error("Old task must not execute") }
    check(!recovered.markFeedbackVisible(pending.taskId, pending.attempt))
    println("RESTART marks INTERRUPTED without resubmission OK")
}
