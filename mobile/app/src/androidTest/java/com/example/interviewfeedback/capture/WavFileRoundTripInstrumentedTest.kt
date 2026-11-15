package com.example.interviewfeedback.capture

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.interviewfeedback.application.Audio
import com.example.interviewfeedback.application.ErrorCode
import com.example.interviewfeedback.application.ModuleFailure
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest

/**
 * 真机文件系统上的 WAV 往返验证。
 * JVM 版 WavRoundTripTest 只覆盖内存流；这里覆盖真实 cacheDir、真实文件句柄与落盘哈希。
 */
@RunWith(AndroidJUnit4::class)
class WavFileRoundTripInstrumentedTest {

    private lateinit var dir: File

    @Before
    fun setUp() {
        dir = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir, "wav-androidtest")
        dir.mkdirs()
    }

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    private fun sampleAudio(samples: Int = 160000) =
        Audio(samples, ByteArray(samples * 2) { (it % 127).toByte() })

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Test
    fun fileRoundTripPreservesSampleCountBytesAndHash() {
        val target = File(dir, "roundtrip.wav")
        val original = sampleAudio()
        target.outputStream().use { WavPcmIO.write(original, it) }

        assertEquals("16 万采样 + 44 字节头", 320044L, target.length())

        val decoded = target.inputStream().use { WavPcmIO.read(it) }
        assertEquals(original.sampleCount, decoded.sampleCount)
        assertEquals(original.pcm.size, decoded.pcm.size)
        assertTrue("落盘再读回后 PCM 必须逐字节一致", original.pcm.contentEquals(decoded.pcm))
        assertEquals("哈希必须稳定", sha256(original.pcm), sha256(decoded.pcm))
    }

    @Test
    fun writtenHeaderIsSixteenKilohertzMonoSixteenBit() {
        val target = File(dir, "header.wav")
        target.outputStream().use { WavPcmIO.write(sampleAudio(16000), it) }
        val fixedHeader = buildMap {
            put(20, 1)   // fmt 块 PCM
            put(22, 1)   // 声道数
            put(24, 16000) // 采样率
            put(34, 16)  // 位深
        }

        val bytes = target.readBytes()
        assertEquals("RIFF", String(bytes, 0, 4, Charsets.US_ASCII))
        assertEquals("WAVE", String(bytes, 8, 4, Charsets.US_ASCII))
        val buffer = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        assertEquals(fixedHeader[20], buffer.getShort(20).toInt())
        assertEquals(fixedHeader[22], buffer.getShort(22).toInt())
        assertEquals(fixedHeader[24], buffer.getInt(24))
        assertEquals(fixedHeader[34], buffer.getShort(34).toInt())
        assertEquals("total 字段必须与文件长度自洽", bytes.size - 8, buffer.getInt(4))
    }

    @Test
    fun truncatedFileOnDiskIsRejected() {
        val target = File(dir, "truncated.wav")
        target.writeBytes(byteArrayOf(1, 2, 3))
        try {
            target.inputStream().use { WavPcmIO.read(it) }
            fail("截断文件必须被拒绝")
        } catch (expected: ModuleFailure) {
            assertEquals(ErrorCode.INVALID_PAYLOAD, expected.code)
        }
    }

    @Test
    fun stereoHeaderOnDiskIsRejected() {
        val target = File(dir, "stereo.wav")
        target.outputStream().use { WavPcmIO.write(sampleAudio(), it) }
        val bytes = target.readBytes()
        bytes[22] = 2
        target.writeBytes(bytes)
        try {
            target.inputStream().use { WavPcmIO.read(it) }
            fail("双声道 WAV 必须被拒绝")
        } catch (expected: ModuleFailure) {
            assertEquals(ErrorCode.INVALID_PAYLOAD, expected.code)
        }
    }
}
