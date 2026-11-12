package com.example.interviewfeedback.experiment

import com.example.interviewfeedback.application.*
import com.example.interviewfeedback.application.Module
import com.example.interviewfeedback.transport.*
import com.example.interviewfeedback.capture.WavPcmIO
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

private fun reject(block: () -> Unit) { var failed = false; try { block() } catch (_: Exception) { failed = true }; check(failed) }
private fun adapter(side: Executor, fail: Boolean = false, cancel: ((ModuleRequest) -> Unit)? = null) = ModuleExecutor { request ->
    cancel?.invoke(request)
    val timing = if (side == Executor.REMOTE) Timing(11, 120, 230, 37, 2, 3) else Timing(7)
    if (fail && request.id.module == Module.M2) ModuleResult.Error(request.id, side, timing, ErrorCode.NO_TRANSCRIPT)
    else {
        val output: ModuleOutput = when (request.id.module) {
            Module.M1 -> (request.payload as Audio).let { Segments(listOf(Segment("seg1",0,it.sampleCount,it.pcm))) }
            Module.M2 -> (request.payload as Segments).let { Transcript("固定测试",it.values.map { s -> TranscriptSegment(s.id,s.start,s.end,"固定测试") }) }
            Module.M3 -> (request.payload as EncodeInput).let { Embeddings(2,listOf(SentenceVector("s1","固定测试",listOf(1.0,0.0))),it.keypoints.map { p -> KeypointVector(p.id,listOf(1.0,0.0)) }) }
            Module.M4 -> Matches(listOf(Match("k1",1.0,true,"s1","固定测试")))
            else -> error("Unexpected module")
        }
        ModuleResult.Ok(request.id,side,timing,output)
    }
}

fun main(args: Array<String>) {
    val directory = File(args.single())
    val store = FileExperimentStore(File(directory,"experiments"))
    val samplesBytes = File(directory,"samples.json").readBytes()
    val catalog = store.saveSamples(samplesBytes)
    val info = JSONObject(File(directory,"device-info.json").readText())
    val manifestHash = info.getJSONObject("runtime").getString("model_manifest_sha256")
    val actual = ExperimentRuntime("jvm-fixture","JVM fixture","n/a","arm64-v8a","0.2.0","a".repeat(40),manifestHash,"model-fixture","rules-fixture")
    val audio = File(directory,"valid.wav").inputStream().use(WavPcmIO::read)
    val wavHash = ExperimentFiles.sha256(File(directory,"valid.wav").readBytes())
    val journal = FileTaskJournal(File(directory,"tasks"))
    val eventsFile = File(directory,"events.jsonl")
    check(!eventsFile.exists()) { "Use fresh evidence directory" }
    val sink = JsonlEventSink(eventsFile)
    val lines = mutableListOf<String>()
    for (mode in PlanMode.values()) {
        val bytes = File(directory,mode.name+".json").readBytes()
        val run = store.saveRun(bytes)
        val bound = ExperimentFiles.bind(run,catalog,null,InputSource.IMPORT,wavHash,actual)
        store.freeze(run,catalog)
        val engine = TaskCoordinator(adapter(Executor.LOCAL),adapter(Executor.REMOTE),journal,sink)
        fun begin(coordinator: TaskCoordinator, b: BoundExperiment = bound) = coordinator.begin(b.plan,InputSource.IMPORT,
            b.runId,b.sample.id,b.sample.effective,submittedAtNanos=System.nanoTime()-8_000_000,experiment=b.link)
        val task = begin(engine)
        engine.run(task.taskId,bound.sample.keypoints,5000,priorAudioPreparationMs=6) { ExperimentFiles.checkAudio(run,audio); audio }
        check(engine.current()?.status == TaskStatus.SUCCEEDED)
        check(engine.markFeedbackVisible(task.taskId,task.attempt))
        val saved = checkNotNull(journal.load(task.taskId))
        val current = checkNotNull(engine.current())
        check(saved.measurements == current.measurements && saved.experiment == current.experiment)
        check(saved.totalElapsedMs == current.totalElapsedMs && saved.feedbackElapsedMs == current.feedbackElapsedMs)
        check(saved.taskId == current.taskId && saved.runId == current.runId && saved.sampleId == current.sampleId)
        check(saved.visible == current.visible && saved.feedback == current.feedback && saved.status == current.status)
        check(saved.plan.assignments == current.plan.assignments && saved.plan.planVersion == current.plan.planVersion)
        check(saved.measurements.map { it.module } == Module.values().toList())
        check(saved.measurements.first().timing.elapsedMs >= 6)
        check(saved.totalElapsedMs != null && saved.feedbackElapsedMs != null)
        val text = TaskMeasurements.text(saved)
        check(text.contains(run.runId) && text.contains("fixture-valid") && text.contains("有效输入"))
        for (measurement in saved.measurements) {
            check(measurement.executor == run.plan.executor(measurement.module))
            if (measurement.executor == Executor.REMOTE) check(text.contains("HTTP往返 37 ms"))
        }
        lines.add(text)
        val failure = TaskCoordinator(adapter(Executor.LOCAL,true),adapter(Executor.REMOTE,true),journal,sink)
        val failed = begin(failure)
        failure.run(failed.taskId,bound.sample.keypoints,5000) { audio }
        check(failure.current()?.error == ErrorCode.NO_TRANSCRIPT && failure.current()?.effectiveInput == true)
        check(failure.current()?.measurements?.last()?.status == "ERROR")
        val silence = ExperimentFiles.bind(run,catalog,"fixture-silence",InputSource.IMPORT,
            catalog.samples.single { it.id == "fixture-silence" }.sha256,actual)
        val bad = ModuleExecutor { request -> ModuleResult.Error(request.id,run.plan.executor(request.id.module),Timing(6,moduleTimeKnown=false),ErrorCode.NO_SPEECH) }
        val invalid = TaskCoordinator(bad,bad,journal,sink)
        val silentTask = begin(invalid,silence)
        invalid.run(silentTask.taskId,silence.sample.keypoints,5000) { audio }
        check(invalid.current()?.effectiveInput == false)
        check(TaskMeasurements.text(checkNotNull(invalid.current())).contains("计算时间未知"))
        lateinit var cancellation: TaskCoordinator
        val onCall: (ModuleRequest) -> Unit = { if (it.id.module == Module.M1) cancellation.cancel(it.id.taskId) }
        cancellation = TaskCoordinator(adapter(Executor.LOCAL,cancel=onCall),adapter(Executor.REMOTE,cancel=onCall),journal,sink)
        val cancelled = begin(cancellation)
        cancellation.run(cancelled.taskId,bound.sample.keypoints,5000) { audio }
        check(cancellation.current()?.status == TaskStatus.CANCELLED)
        check(cancellation.current()?.measurements?.map { it.module } == listOf(Module.M0))
        val pending = begin(engine)
        TaskCoordinator(adapter(Executor.LOCAL),adapter(Executor.REMOTE),journal,sink)
        check(journal.load(pending.taskId)?.status == TaskStatus.INTERRUPTED)
        check(journal.load(pending.taskId)?.experiment == bound.link)
        reject { ExperimentFiles.bind(run,catalog,null,InputSource.IMPORT,"0".repeat(64),actual) }
        reject { ExperimentFiles.bind(run,catalog,null,InputSource.IMPORT,wavHash,actual.copy(deviceId="other-device")) }
        reject { ExperimentFiles.bind(run,catalog,null,InputSource.IMPORT,wavHash,actual.copy(modelManifestSha256="0".repeat(64))) }
        reject { ExperimentFiles.bind(run,catalog,null,InputSource.RECORDING,null,actual) }
        val changed = JSONObject(bytes.toString(Charsets.UTF_8)).apply { getJSONObject("runtime").put("warmup","WARM") }
        reject { store.freeze(store.saveRun(changed.toString().toByteArray()),catalog) }
        println(mode.name + " timing persistence, UI text, success/failure/cancel/restart linkage OK")
    }
    val duplicate = JSONArray(samplesBytes.toString(Charsets.UTF_8)).apply { getJSONObject(1).put("sha256",wavHash) }
    val duplicateCatalog = ExperimentFiles.samples(duplicate.toString().toByteArray())
    val baseRun = ExperimentFiles.run(File(directory,"LOCAL.json").readBytes()).copy(sampleManifestSha256=duplicateCatalog.sha256)
    reject { ExperimentFiles.bind(baseRun,duplicateCatalog,null,InputSource.IMPORT,wavHash,actual) }
    check(ExperimentFiles.bind(baseRun,duplicateCatalog,"fixture-valid",InputSource.IMPORT,wavHash,actual).sample.id == "fixture-valid")
    reject { ExperimentFiles.bind(baseRun.copy(condition="FORMAL"),duplicateCatalog,"fixture-valid",InputSource.IMPORT,wavHash,actual) }
    val recording = baseRun.copy(source=InputSource.RECORDING)
    check(ExperimentFiles.bind(recording,duplicateCatalog,"fixture-valid",InputSource.RECORDING,"0".repeat(64),actual).link.actualWavSha256 == "0".repeat(64))
    val invalidClass = JSONArray(samplesBytes.toString(Charsets.UTF_8)).apply { getJSONObject(0).put("effective_input","true") }
    reject { ExperimentFiles.samples(invalidClass.toString().toByteArray()) }
    store.export(eventsFile,File(directory,"experiment-records.zip").outputStream())
    File(directory,"measurement-panel.txt").writeText(lines.joinToString("\n\n"),Charsets.UTF_8)
    println("Automatic hash binding, duplicate-hash rejection, frozen run and exact event/measurement export OK (FIXTURE only)")
}
