package com.example.interviewfeedback.transport

import com.example.interviewfeedback.application.*
import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.*
import org.junit.Test

class RemoteTimeoutTest {
    private fun request(budget: Int) = ModuleRequest(
        CallId("timeout-test", 1, Module.M2, "test-plan", "test-model", "test-rules"),
        budget, Segments(listOf(Segment("seg1", 0, 1, byteArrayOf(0, 0)))),
    )

    private fun delayedServer(delayMs: Long, test: (RemoteExecutor) -> Unit) {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/api/v1/modules/M2/execute") { exchange ->
            exchange.requestBody.use { it.readBytes() }
            Thread.sleep(delayMs)
            val body = """{"schema_version":1,"task_id":"timeout-test","attempt":1,"module_id":"M2","plan_version":"test-plan","model_version":"test-model","config_version":"test-rules","executor":"REMOTE","status":"OK","elapsed_ms":$delayMs,"output":{"transcript":{"full_text":"hello","segments":[{"segment_id":"seg1","start_sample":0,"end_sample":1,"text":"hello"}]}}}""".toByteArray()
            try {
                exchange.sendResponseHeaders(200, body.size.toLong())
                exchange.responseBody.use { it.write(body) }
            } catch (_: java.io.IOException) { /* Client deadline may close the socket. */ }
            finally { exchange.close() }
        }
        server.start()
        try { test(RemoteExecutor("http://127.0.0.1:${server.address.port}".toHttpUrl(), "test-token")) }
        finally { server.stop(0) }
    }

    @Test fun responseAfterDefaultReadTimeoutSucceedsWithinBudget() = delayedServer(11000) {
        val result = it.execute(request(15000))
        assertTrue("A valid response after 10 seconds must succeed: $result", result is ModuleResult.Ok)
        assertEquals("hello", ((result as ModuleResult.Ok).output as Transcript).fullText)
    }

    @Test fun totalCallBudgetStillExpires() = delayedServer(1500) {
        val started = System.nanoTime()
        val result = it.execute(request(300))
        val elapsed = (System.nanoTime() - started) / 1_000_000
        assertTrue(result is ModuleResult.Error)
        assertEquals(ErrorCode.DEADLINE_EXCEEDED, (result as ModuleResult.Error).code)
        assertTrue("Call budget was not enforced: $elapsed ms", elapsed < 1400)
    }
}
