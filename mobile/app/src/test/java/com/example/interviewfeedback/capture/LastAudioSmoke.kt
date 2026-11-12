package com.example.interviewfeedback.capture

import com.example.interviewfeedback.application.Audio
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

private fun reject(block: () -> Unit) {
    var failed = false
    try { block() } catch (_: Exception) { failed = true }
    check(failed)
}
fun main(args: Array<String>) {
    val directory = File(args.single()).apply { mkdirs() }
    val file = File(directory, "last.wav")
    check(!file.exists()) { "Use fresh evidence directory" }
    val audio = Audio(1600, ByteArray(3200) { (it % 127).toByte() })
    val absent = LastAudioStore(file)
    check(!absent.available())
    reject { absent.export(ByteArrayOutputStream()) }
    // Existing APK 0.2.0 writes this plain last.wav: the update must reuse it.
    file.outputStream().use { WavPcmIO.write(audio, it) }
    val legacy = file.readBytes()
    val afterRecreation = LastAudioStore(file)
    check(afterRecreation.available())
    val first = ByteArrayOutputStream().also(afterRecreation::export).toByteArray()
    check(first.contentEquals(legacy))
    check(WavPcmIO.read(ByteArrayInputStream(first)).pcm.contentEquals(audio.pcm))
    println("Existing 0.2.0 last.wav exported after store/Activity recreation OK")
    val replacement = Audio(3200, ByteArray(6400) { 42 })
    afterRecreation.save(replacement)
    val second = ByteArrayOutputStream().also { LastAudioStore(file).export(it) }.toByteArray()
    check(second.size == 6444)
    check(WavPcmIO.read(ByteArrayInputStream(second)).pcm.contentEquals(replacement.pcm))
    reject { afterRecreation.save(Audio(5, ByteArray(1))) }
    check(file.readBytes().contentEquals(second))
    check(directory.listFiles()!!.none { it.extension == "tmp" })
    println("Atomic save and invalid-save preservation OK")
    val corrupt = File(directory, "corrupt.wav").apply { writeBytes(ByteArray(44)) }
    val untouched = ByteArrayOutputStream()
    reject { LastAudioStore(corrupt).export(untouched) }
    check(untouched.size() == 0)
    File(directory, "exported.wav").writeBytes(second)
    println("Missing/corrupt input rejected; validated WAV bytes exported without memory-only fields OK")
}
