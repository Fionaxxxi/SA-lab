package com.example.interviewfeedback.analysis.semantic

class SentencePiece(path: String) : AutoCloseable {
    private var handle = open(path)
    init { require(handle != 0L) }
    fun encode(text: String): IntArray = encodeNative(handle, text)
    override fun close() { if (handle != 0L) { destroy(handle); handle = 0 } }
    private external fun open(path: String): Long
    private external fun encodeNative(handle: Long, text: String): IntArray
    private external fun destroy(handle: Long)
    companion object { init { System.loadLibrary("interview_tokenizer") } }
}
