package com.example.interviewfeedback.application

import com.example.interviewfeedback.capture.WavPcmIO
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

/**
 * JVM 单测版 WAV 往返验证，逻辑与原 WavSmoke.kt (fun main) 一致。
 * 原 smoke 保留不动，本文件只把它纳入 testDebugUnitTest 的用例统计。
 */
class WavRoundTripTest {

    @Test
    fun roundTripPreservesSampleCountAndPcmBytes() {
        val original = Audio(160000, ByteArray(320000) { (it % 127).toByte() })
        val encoded = ByteArrayOutputStream()
        WavPcmIO.write(original, encoded)
        val bytes = encoded.toByteArray()

        assertEquals("32 万采样点加 44 字节头", 320044, bytes.size)

        val decoded = WavPcmIO.read(ByteArrayInputStream(bytes))
        assertEquals(original.sampleCount, decoded.sampleCount)
        assertTrue("PCM 内容必须逐字节一致", decoded.pcm.contentEquals(original.pcm))
    }

    @Test
    fun stereoWavIsRejected() {
        val original = Audio(160000, ByteArray(320000) { (it % 127).toByte() })
        val encoded = ByteArrayOutputStream()
        WavPcmIO.write(original, encoded)
        val bytes = encoded.toByteArray()
        bytes[22] = 2
        try {
            WavPcmIO.read(ByteArrayInputStream(bytes))
            fail("双声道 WAV 必须被拒绝")
        } catch (_: ModuleFailure) {
            // 预期行为
        }
    }

    @Test
    fun truncatedWavIsRejected() {
        try {
            WavPcmIO.read(ByteArrayInputStream(byteArrayOf(1, 2)))
            fail("截断文件必须被拒绝")
        } catch (_: ModuleFailure) {
            // 预期行为
        }
    }
}
