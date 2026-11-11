package com.example.interviewfeedback.capture

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.example.interviewfeedback.application.Audio
import java.io.ByteArrayOutputStream

class InterviewAudioRecorder {
    @Volatile private var running = false
    private var worker: Thread? = null
    private var recorder: AudioRecord? = null
    private var result: Audio? = null
    private var failure: Throwable? = null

    @Synchronized fun start() {
        check(worker == null)
        val minimum = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        require(minimum > 0)
        val capture = AudioRecord(MediaRecorder.AudioSource.MIC, 16000, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(8192, minimum))
        check(capture.state == AudioRecord.STATE_INITIALIZED)
        capture.startRecording()
        recorder = capture
        running = true
        failure = null
        result = null
        worker = Thread {
            val output = ByteArrayOutputStream()
            try {
                val buffer = ByteArray(4096)
                while (running && output.size() < 1_920_000) {
                    val count = capture.read(buffer, 0, minOf(buffer.size, 1_920_000 - output.size()))
                    if (count < 0) {
                        if (running) error("AudioRecord read failed: $count")
                        break
                    }
                    if (count > 0) output.write(buffer, 0, count)
                }
                val pcm = output.toByteArray()
                result = Audio(pcm.size / 2, pcm)
            } catch (error: Throwable) {
                failure = error
            } finally {
                running = false
                try { capture.stop() } catch (_: IllegalStateException) {}
                capture.release()
            }
        }.also { it.start() }
    }

    fun stop(): Audio {
        running = false
        worker?.join()
        worker = null
        recorder = null
        failure?.let { throw it }
        return checkNotNull(result)
    }
}
