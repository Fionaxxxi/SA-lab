package com.example.interviewfeedback.capture

import com.example.interviewfeedback.application.Audio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * JVM 单测版 last.wav 持久化验证，逻辑与原 LastAudioSmoke.kt (fun main) 一致。
 * 用 TemporaryFolder 替代原 smoke 要求的"调用方传入全新目录"。
 */
class LastAudioStoreTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private fun reject(block: () -> Unit) {
        var failed = false
        try {
            block()
        } catch (_: Exception) {
            failed = true
        }
        if (!failed) fail("该操作应当抛异常")
    }

    @Test
    fun legacyWavExportedAfterStoreRecreation() {
        val file = File(tmp.root, "last.wav")
        assertFalse("测试目录必须是全新的", file.exists())

        val audio = Audio(1600, ByteArray(3200) { (it % 127).toByte() })
        val absent = LastAudioStore(file)
        assertFalse(absent.available())
        reject { absent.export(ByteArrayOutputStream()) }

        // 0.2.0 版 APK 写入的是明文 last.wav，升级后必须能复用
        file.outputStream().use { WavPcmIO.write(audio, it) }
        val legacy = file.readBytes()

        val afterRecreation = LastAudioStore(file)
        assertTrue(afterRecreation.available())

        val first = ByteArrayOutputStream().also(afterRecreation::export).toByteArray()
        assertTrue("导出字节必须与原文件一致", first.contentEquals(legacy))
        assertTrue(WavPcmIO.read(ByteArrayInputStream(first)).pcm.contentEquals(audio.pcm))
    }

    @Test
    fun atomicSaveAndInvalidSavePreservesOriginal() {
        val file = File(tmp.root, "last.wav")
        val audio = Audio(1600, ByteArray(3200) { (it % 127).toByte() })
        file.outputStream().use { WavPcmIO.write(audio, it) }
        val store = LastAudioStore(file)

        val replacement = Audio(3200, ByteArray(6400) { 42 })
        store.save(replacement)

        val second = ByteArrayOutputStream().also { LastAudioStore(file).export(it) }.toByteArray()
        assertEquals("6400 字节 PCM 加 44 字节头", 6444, second.size)
        assertTrue(WavPcmIO.read(ByteArrayInputStream(second)).pcm.contentEquals(replacement.pcm))

        reject { store.save(Audio(5, ByteArray(1))) }
        assertTrue("无效保存不得覆盖已有文件", file.readBytes().contentEquals(second))
        assertTrue("不得残留 .tmp 中间文件", tmp.root.listFiles()!!.none { it.extension == "tmp" })
    }

    @Test
    fun corruptInputRejectedWithoutWritingOutput() {
        val corrupt = File(tmp.root, "corrupt.wav").apply { writeBytes(ByteArray(44)) }
        val untouched = ByteArrayOutputStream()
        reject { LastAudioStore(corrupt).export(untouched) }
        assertEquals("拒绝时不得写出任何字节", 0, untouched.size())
    }
}
