package com.example.interviewfeedback.application

/** Immutable values shared by persistence, events and the measurement panel. */
data class ModuleMeasurement(val module: Module, val executor: Executor, val status: String,
    val timing: Timing, val error: ErrorCode? = null)

data class ExperimentLink(val condition: String, val runConfigSha256: String,
    val sampleManifestSha256: String, val sampleSha256: String, val topicId: String,
    val split: String, val actualWavSha256: String? = null)

object TaskMeasurements {
    fun text(task: TaskRecord): String = buildString {
        append("任务 ").append(task.taskId).append("\n运行 ").append(task.runId)
        append("\n样本 ").append(task.sampleId).append(" · ")
        append(when (task.effectiveInput) { true -> "有效输入"; false -> "无效输入"; null -> "未分类" })
        task.experiment?.let { append("\n实验 ").append(it.condition).append(" · 题目 ").append(it.topicId).append(" · ").append(it.split) }
        append("\n状态 ").append(task.status.name)
        task.totalElapsedMs?.let { append(" · 到结果保存 ").append(it).append(" ms") }
        task.feedbackElapsedMs?.let { append("\n到完整反馈 ").append(it).append(" ms") }
        for (module in Module.values()) {
            val item = task.measurements.lastOrNull { it.module == module }
            append("\n").append(module.name).append(" · ")
            append(if (task.plan.executor(module) == Executor.LOCAL) "手机本地" else "电脑远程")
            if (item == null) {
                append(if (task.status in setOf(TaskStatus.CREATED, TaskStatus.RUNNING)) " · 等待" else " · 无采纳记录")
            } else {
                append(" · ").append(item.status)
                append(if (item.timing.moduleTimeKnown) " · 节点 " else " · 调用耗时（计算时间未知） ")
                append(item.timing.elapsedMs).append(" ms")
                item.timing.roundTripMs?.let { append(" · HTTP往返 ").append(it).append(" ms") }
                item.timing.encodeMs?.let { append(" · 序列化 ").append(it).append(" ms") }
                item.timing.decodeMs?.let { append(" · 解码 ").append(it).append(" ms") }
                item.error?.let { append(" · ").append(it.name) }
            }
        }
    }
}
