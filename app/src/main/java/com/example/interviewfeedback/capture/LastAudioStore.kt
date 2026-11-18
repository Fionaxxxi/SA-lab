package com.example.interviewfeedback.capture

import com.example.interviewfeedback.application.Audio
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** App-private durable recording; independent of Activity fields and file-picker recreation. */
class LastAudioStore(private val file: File) {
    fun available(): Boolean = file.isFile && file.length() >= 44

    @Synchronized fun save(audio: Audio) {
        val directory = checkNotNull(file.parentFile)
        require(directory.isDirectory || directory.mkdirs())
        val temporary = File.createTempFile("audio-", ".tmp", directory)
        try {
            FileOutputStream(temporary).use { output ->
                WavPcmIO.write(audio, output)
                output.fd.sync()
            }
            Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } finally { temporary.delete() }
    }

    @Synchronized fun export(output: OutputStream) {
        check(file.isFile) { "尚无已保存录音，请先完成一次录音或导入" }
        // Validate before touching the target so corrupt input never becomes a successful empty export.
        val audio = file.inputStream().use(WavPcmIO::read)
        WavPcmIO.write(audio, output)
    }
}
