package com.example.interviewfeedback.capture

import com.example.interviewfeedback.application.Audio
import com.example.interviewfeedback.application.ModuleFailure
import com.example.interviewfeedback.application.ErrorCode
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

object WavPcmIO {
    fun read(input: InputStream): Audio {
        val bytes = input.readBytesBounded(2_000_000)
        fun fail(): Nothing = throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
        if (bytes.size < 44) fail()
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        fun tag(offset: Int) = String(bytes, offset, 4, Charsets.US_ASCII)
        if (tag(0) != "RIFF" || tag(8) != "WAVE" || buffer.getInt(4).toLong() + 8 != bytes.size.toLong()) fail()
        var offset = 12
        var validFormat = false
        var pcm: ByteArray? = null
        while (offset + 8 <= bytes.size) {
            val size = buffer.getInt(offset + 4)
            val end = offset.toLong() + 8 + size
            if (size < 0 || end > bytes.size) fail()
            when (tag(offset)) {
                "fmt " -> {
                    if (size < 16 || buffer.getShort(offset + 8).toInt() != 1 ||
                        buffer.getShort(offset + 10).toInt() != 1 || buffer.getInt(offset + 12) != 16000 ||
                        buffer.getInt(offset + 16) != 32000 || buffer.getShort(offset + 20).toInt() != 2 ||
                        buffer.getShort(offset + 22).toInt() != 16) fail()
                    validFormat = true
                }
                "data" -> {
                    if (pcm != null) fail()
                    pcm = bytes.copyOfRange(offset + 8, end.toInt())
                }
            }
            offset = (end + size % 2).toInt()
        }
        val data = pcm ?: fail()
        if (!validFormat || data.isEmpty() || data.size % 2 != 0 || data.size > 1_920_000) fail()
        return Audio(data.size / 2, data)
    }

    fun write(audio: Audio, output: OutputStream) {
        require(audio.sampleCount in 1..960000 && audio.pcm.size == audio.sampleCount * 2)
        val head = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        head.put("RIFF".toByteArray()).putInt(36 + audio.pcm.size).put("WAVEfmt ".toByteArray())
        head.putInt(16).putShort(1).putShort(1).putInt(16000).putInt(32000).putShort(2).putShort(16)
        head.put("data".toByteArray()).putInt(audio.pcm.size)
        output.write(head.array())
        output.write(audio.pcm)
    }

    private fun InputStream.readBytesBounded(limit: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream()
        val chunk = ByteArray(8192)
        while (true) {
            val count = read(chunk)
            if (count < 0) break
            if (output.size() + count > limit) throw ModuleFailure(ErrorCode.INVALID_PAYLOAD)
            output.write(chunk, 0, count)
        }
        return output.toByteArray()
    }
}
