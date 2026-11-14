package com.example.interviewfeedback.application

import com.example.interviewfeedback.transport.FileTaskJournal
import com.example.interviewfeedback.transport.JsonlEventSink
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * JVM 单测版协调器验证，取自 CoordinatorSmoke.kt (fun main) 的 LOCAL 与故障路径。
 *
 * 与原 smoke 的差异：原 smoke 用真实 RemoteExecutor 打 HTTP，覆盖 REMOTE 三模式；
 * 这里把 remote 换成回落到本地的 stub，只跑 LOCAL 计划，因为 REMOTE 分支需要
 * WireJson 走 org.json，而 src/test 下的 org.json 会被 android.jar 的 throw-stub 覆盖。
 * REMOTE / MANUAL_MIXED 的端到端验证归入 androidTest。
 */
class CoordinatorPlanTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val text = "先调查居民需求"
    private val keypoints = listOf(Keypoint("k1", text))
    private val audio = Audio(2, byteArrayOf(1, 2, 3, 4))

    private inner class Fixtures : LocalModules {
        override fun vad(audio: Audio, id: CallId) =
            Segments(listOf(Segment("seg1", 0, audio.sampleCount, audio.pcm)))

        override fun asr(segments: Segments, id: CallId) =
            Transcript(text, segments.values.map { TranscriptSegment(it.id, it.start, it.end, text) })

        override fun encode(input: EncodeInput, id: CallId) = Embeddings(
            2, listOf(SentenceVector("s1", text, listOf(1.0, 0.0))),
            input.keypoints.map { KeypointVector(it.id, listOf(1.0, 0.0)) })

        override fun match(embeddings: Embeddings, id: CallId) =
            Matches(embeddings.keypoints.map { Match(it.id, 1.0, true, "s1", text) })
    }

    private fun plan(mode: PlanMode, nodes: Set<Module> = emptySet()) = ExecutionPlan(
        "plan-${mode.name}", "jvm-fixture", "modelset-demo", "rules-demo", mode, nodes)

    private class Harness(
        val coordinator: TaskCoordinator,
        val journal: FileTaskJournal,
        val events: MutableList<TaskEvent>,
        val dir: File,
    )

    private fun harness(): Harness {
        val dir = tmp.newFolder()
        val sink = JsonlEventSink(File(dir, "coordinator.jsonl"))
        val events = mutableListOf<TaskEvent>()
        val capture = EventSink { events.add(it); sink.append(it) }
        val journal = FileTaskJournal(File(dir, "tasks"))
        val local = LocalExecutor(Fixtures())
        val remoteStub = ModuleExecutor { request -> local.execute(request) }
        return Harness(TaskCoordinator(local, remoteStub, journal, capture), journal, events, dir)
    }

    @Test
    fun localPlanSucceedsWithExpectedFeedbackAndEventOrder() {
        val h = harness()
        val configuration = plan(PlanMode.LOCAL)
        val task = h.coordinator.begin(
            configuration, InputSource.IMPORT, "demo-local", "synthetic-pcm", true)
        h.coordinator.run(task.taskId, keypoints, 5000) { audio }

        val result = h.coordinator.current()
        assertNotNull("任务结果必须存在", result)
        assertEquals(TaskStatus.SUCCEEDED, result!!.status)
        assertEquals(
            Feedback(
                Transcript(text, listOf(TranscriptSegment("seg1", 0, 2, text))),
                Matches(listOf(Match("k1", 1.0, true, "s1", text)))),
            result.feedback)

        assertEquals(TaskStatus.SUCCEEDED, h.journal.load(task.taskId)?.status)
        assertEquals(result.feedback, h.journal.load(task.taskId)?.feedback)

        assertTrue("首次标记反馈可见必须成功", h.coordinator.markFeedbackVisible(task.taskId, task.attempt))
        assertFalse("重复标记必须被拒绝", h.coordinator.markFeedbackVisible(task.taskId, task.attempt))

        val moduleEnds = h.events.filter { it.task.taskId == task.taskId && it.event == "MODULE_END" }
        assertEquals("五个模块的结束事件必须齐全且顺序固定",
            Module.values().toList(), moduleEnds.map { it.module })

        for (event in moduleEnds) {
            val module = event.module
            assertNotNull("每个结束事件都必须带模块号", module)
            assertEquals(configuration.executor(module!!), event.executor)
            val timing = event.timing
            assertNotNull("每个结束事件都必须带计时", timing)
            if (event.executor == Executor.LOCAL) {
                assertEquals("LOCAL 不得记录上行字节", 0L, timing!!.bytesUp)
                assertEquals("LOCAL 不得记录下行字节", 0L, timing.bytesDown)
                assertNull("LOCAL 不得记录往返时延", timing.roundTripMs)
            }
        }
    }

    @Test
    fun cancelMakesLateOutputIgnored() {
        val h = harness()
        val local = LocalExecutor(Fixtures())
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val blocked = ModuleExecutor { request ->
            started.countDown()
            assertTrue(release.await(3, TimeUnit.SECONDS))
            local.execute(request)
        }
        val cancellation = TaskCoordinator(blocked, blocked, h.journal, EventSink { h.events.add(it) })

        val task = cancellation.begin(plan(PlanMode.LOCAL), InputSource.RECORDING, "demo-fault-recording", "cancel")
        val worker = thread { cancellation.run(task.taskId, keypoints, 5000) { audio } }
        try {
            assertTrue("任务必须已进入执行阶段", started.await(3, TimeUnit.SECONDS))
            assertTrue("取消请求必须被接受", cancellation.cancel(task.taskId))
            assertEquals(TaskStatus.CANCELLED, h.journal.load(task.taskId)?.status)
        } finally {
            release.countDown()
            worker.join()
        }
        assertNull("取消后不得产出反馈", h.journal.load(task.taskId)?.feedback)
        assertTrue("迟到输出必须被记为 IGNORED",
            h.events.any { it.task.taskId == task.taskId && it.status == "IGNORED" })
    }

    @Test
    fun oldAttemptResultIsRejectedAsVersionMismatch() {
        val h = harness()
        val local = LocalExecutor(Fixtures())
        val stale = ModuleExecutor { request ->
            val actual = local.execute(request) as ModuleResult.Ok
            actual.copy(id = actual.id.copy(attempt = 2))
        }
        val guarded = TaskCoordinator(stale, stale, h.journal, EventSink { h.events.add(it) })
        val task = guarded.begin(plan(PlanMode.LOCAL), InputSource.IMPORT, "demo-fault-import", "stale")
        guarded.run(task.taskId, keypoints, 5000) { audio }

        assertEquals(ErrorCode.VERSION_MISMATCH, h.journal.load(task.taskId)?.error)
        assertNull("旧 attempt 的结果不得进入反馈", h.journal.load(task.taskId)?.feedback)
    }

    @Test
    fun invalidPcmFailsWithInvalidPayload() {
        val h = harness()
        val task = h.coordinator.begin(plan(PlanMode.LOCAL), InputSource.IMPORT, "demo-fault-import", "invalid", false)
        h.coordinator.run(task.taskId, keypoints, 5000) { Audio(5, ByteArray(1)) }
        assertEquals(ErrorCode.INVALID_PAYLOAD, h.journal.load(task.taskId)?.error)
    }

    @Test
    fun restartMarksInterruptedWithoutResubmission() {
        val h = harness()
        val pending = h.coordinator.begin(plan(PlanMode.LOCAL), InputSource.IMPORT, "demo-fault-import", "interrupted")

        val reopened = FileTaskJournal(File(h.dir, "tasks"))
        val local = LocalExecutor(Fixtures())
        val remoteStub = ModuleExecutor { request -> local.execute(request) }
        // 恢复逻辑发生在 TaskCoordinator 构造期，必须先构造再断言
        val recovered = TaskCoordinator(local, remoteStub, reopened, EventSink { h.events.add(it) })

        assertEquals("未完成任务在重启时必须标记为 INTERRUPTED",
            TaskStatus.INTERRUPTED, reopened.load(pending.taskId)?.status)

        recovered.run(pending.taskId, keypoints, 5000) { error("重启后旧任务不得重新执行") }
        assertFalse("中断任务不得被标记为反馈可见",
            recovered.markFeedbackVisible(pending.taskId, pending.attempt))
    }
}
