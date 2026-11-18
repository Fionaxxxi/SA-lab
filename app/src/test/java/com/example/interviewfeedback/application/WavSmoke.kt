package com.example.interviewfeedback.application

import com.example.interviewfeedback.capture.WavPcmIO
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

fun main() {
    val original = Audio(160000, ByteArray(320000) { (it % 127).toByte() })
    val encoded = ByteArrayOutputStream()
    WavPcmIO.write(original, encoded)
    val bytes = encoded.toByteArray()
    check(bytes.size == 320044)
    val decoded = WavPcmIO.read(ByteArrayInputStream(bytes))
    check(decoded.sampleCount == original.sampleCount && decoded.pcm.contentEquals(original.pcm))
    bytes[22] = 2
    try { WavPcmIO.read(ByteArrayInputStream(bytes)); error("Stereo WAV accepted") }
    catch (_: ModuleFailure) {}
    try { WavPcmIO.read(ByteArrayInputStream(byteArrayOf(1, 2))); error("Invalid WAV accepted") }
    catch (_: ModuleFailure) {}
    println("WAV roundtrip, byte count, stereo rejection and truncated file rejection OK")
}
