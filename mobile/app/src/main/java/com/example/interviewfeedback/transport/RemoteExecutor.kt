package com.example.interviewfeedback.transport

import com.example.interviewfeedback.application.*
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InterruptedIOException
import java.util.concurrent.TimeUnit
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink
import org.json.JSONObject

class RemoteExecutor(
    private val baseUrl: HttpUrl,
    private val token: String,
    client: OkHttpClient = OkHttpClient(),
) : ModuleExecutor {
    private val http = client.newBuilder()
        .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build()

    init {
        require(baseUrl.username.isEmpty() && baseUrl.password.isEmpty())
        require(token.isNotBlank() && token.all { it.code in 33..126 })
    }

    override fun execute(request: ModuleRequest): ModuleResult {
        val started = nowMs()
        val id = request.id
        var up = 0L
        var down = 0L
        var encodeMs: Long? = null
        var decodeMs: Long? = null
        var networkStart: Long? = null
        var roundTripMs: Long? = null

        fun timing(elapsed: Long?, known: Boolean = elapsed != null) = Timing(
            elapsed ?: 0L, up, down, roundTripMs ?: networkStart?.let { nowMs() - it }, encodeMs, decodeMs, known)
        fun fail(code: ErrorCode, elapsed: Long? = null) =
            ModuleResult.Error(id, Executor.REMOTE, timing(elapsed, known = false), code)

        try {
            val body = WireJson.request(request).toString().toByteArray(Charsets.UTF_8)
            encodeMs = nowMs() - started
            if (body.size > MAX_BODY) return fail(ErrorCode.PAYLOAD_TOO_LARGE)
            val remaining = request.remainingBudgetMs - encodeMs
            if (remaining <= 0) return fail(ErrorCode.DEADLINE_EXCEEDED)
            val requestBody = object : RequestBody() {
                override fun contentType() = JSON_TYPE
                override fun contentLength(): Long = body.size.toLong()
                override fun writeTo(sink: BufferedSink) {
                    var offset = 0
                    while (offset < body.size) {
                        val size = minOf(8192, body.size - offset)
                        sink.write(body, offset, size)
                        offset += size
                        up += size
                    }
                }
            }
            val endpoint = baseUrl.newBuilder()
                .encodedPath("/api/v1/modules/${id.module.name}/execute").query(null).fragment(null).build()
            val outgoing = Request.Builder().url(endpoint).header("Authorization", "Bearer $token")
                .header("Accept-Encoding", "identity").post(requestBody).build()
            val call = http.newCall(outgoing)
            call.timeout().timeout(remaining, TimeUnit.MILLISECONDS)
            networkStart = nowMs()
            call.execute().use { response ->
                val source = response.body ?: return fail(ErrorCode.INVALID_PAYLOAD)
                if (source.contentLength() > MAX_BODY) return fail(ErrorCode.PAYLOAD_TOO_LARGE)
                val bytes = ByteArrayOutputStream()
                source.byteStream().use { input ->
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        down += count
                        if (down > MAX_BODY) return fail(ErrorCode.PAYLOAD_TOO_LARGE)
                        bytes.write(buffer, 0, count)
                    }
                }
                roundTripMs = nowMs() - checkNotNull(networkStart)
                val decodeStart = nowMs()
                val data = JSONObject(bytes.toByteArray().toString(Charsets.UTF_8))
                val status = data.getString("status")
                val serverMs = data.getLong("elapsed_ms")
                require(serverMs >= 0 && data.getString("executor") == "REMOTE")
                if (status == "ERROR" && !response.isSuccessful) {
                    val code = ErrorCode.valueOf(data.getJSONObject("error").getString("code"))
                    // Early gateway errors may omit identity fields it could not safely parse.
                    val sent = WireJson.request(request)
                    for (key in listOf("schema_version", "task_id", "attempt", "module_id",
                        "plan_version", "model_version", "config_version")) {
                        if (!data.isNull(key) && sent.get(key) != data.get(key))
                            return fail(ErrorCode.VERSION_MISMATCH)
                    }
                    decodeMs = nowMs() - decodeStart
                    return fail(code, serverMs)
                }
                if (status != "OK" || !response.isSuccessful) return fail(ErrorCode.INVALID_PAYLOAD)
                if (WireJson.identity(data) != id) return fail(ErrorCode.VERSION_MISMATCH)
                val output = WireJson.output(id.module, data.getJSONObject("output"))
                decodeMs = nowMs() - decodeStart
                if (nowMs() - started >= request.remainingBudgetMs) return fail(ErrorCode.DEADLINE_EXCEEDED)
                return ModuleResult.Ok(id, Executor.REMOTE, timing(serverMs), output)
            }
        } catch (_: InterruptedIOException) {
            return fail(ErrorCode.DEADLINE_EXCEEDED)
        } catch (_: IOException) {
            return fail(ErrorCode.REMOTE_UNREACHABLE)
        } catch (_: Exception) {
            return fail(ErrorCode.INVALID_PAYLOAD)
        }
    }

    private companion object {
        const val MAX_BODY = 4 * 1024 * 1024
        val JSON_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
