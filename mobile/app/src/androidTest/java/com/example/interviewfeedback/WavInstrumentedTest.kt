package com.example.interviewfeedback

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.interviewfeedback.application.Audio
import com.example.interviewfeedback.capture.LastAudioStore
import com.example.interviewfeedback.capture.WavPcmIO
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * 设备端最小冒烟：验证 WAV 编解码与 last.wav 持久化在真实 Android 运行时（不是 JVM stub）可用。
 *
 * 与 src/test 的 JVM 用例互补：
 *  - JVM 用例证明算法逻辑正确；
 *  - 本用例证明同一套代码在设备上的 android.jar 与文件系统里同样成立。
 *
 * 运行方式（需连接真机，arm64-v8a）：
 *   gradle :app:connectedDebugAndroidTest
 */
@RunWith(AndroidJUnit4::class)
class WavInstrumentedTest {

    private fun tempWav(): File {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val dir = File(context.cacheDir, "instrumented-wav-${System.nanoTime()}")
        dir.mkdirs()
        return File(dir, "last.wav")
    }

    @Test
    fun wavRoundTripOnDevice() {
        val original = Audio(16000, ByteArray(32000) { (it % 127).toByte() })
        val encoded = ByteArrayOutputStream()
        WavPcmIO.write(original, encoded)
        val bytes = encoded.toByteArray()
        assertEquals("16000 采样点加 44 字节头", 32044, bytes.size)

        val decoded = WavPcmIO.read(ByteArrayInputStream(bytes))
        assertEquals(original.sampleCount, decoded.sampleCount)
        assertTrue("设备端 PCM 必须逐字节一致", decoded.pcm.contentEquals(original.pcm))
    }

    @Test
    fun lastAudioStoreWorksOnDeviceFilesystem() {
        val file = tempWav()
        assertFalse("测试目录必须是全新的", file.exists())

        val audio = Audio(1600, ByteArray(3200) { (it % 127).toByte() })
        val store = LastAudioStore(file)
        assertFalse("尚未写入时不可用", store.available())

        store.save(audio)
        assertTrue("写入后必须可导出", LastAudioStore(file).available())

        val out = ByteArrayOutputStream()
        LastAudioStore(file).export(out)
        assertTrue("导出字节必须能被解码回原始 PCM",
            WavPcmIO.read(ByteArrayInputStream(out.toByteArray())).pcm.contentEquals(audio.pcm))
        assertTrue("不得残留临时文件", file.parentFile!!.listFiles()!!.none { it.extension == "tmp" })
    }
}
