package com.example.interviewfeedback.ui

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.content.res.ColorStateList
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.*
import com.example.interviewfeedback.application.*

/** Presentation only: all business actions remain in MainActivity. */
class MobileScreen(private val host: Activity, private val action: (String) -> Unit) {
    private val ink = Color.rgb(25, 43, 53)
    private val muted = Color.rgb(103, 120, 130)
    private val teal = Color.rgb(13, 119, 111)
    private val canvas = Color.rgb(244, 247, 247)
    private val handler = Handler(Looper.getMainLooper())
    private var started = 0L
    private var recording = false
    private fun dp(n: Int) = (n * host.resources.displayMetrics.density).toInt()
    private fun shape(color: Int, radius: Int = 20) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat()
    }
    private fun touchBackground(color: Int) = RippleDrawable(ColorStateList.valueOf(0x22000000), shape(color, 14), null)
    private fun column() = LinearLayout(host).apply { orientation = LinearLayout.VERTICAL }
    private fun text(value: String, size: Float = 14f, color: Int = ink, bold: Boolean = false) =
        TextView(host).apply {
            text = value; textSize = size; setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setLineSpacing(dp(3).toFloat(), 1f)
        }
    private fun LinearLayout.put(view: View, top: Int = 0) {
        addView(view, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top) })
    }
    private fun card(parent: LinearLayout): LinearLayout = column().apply {
        setPadding(dp(20), dp(20), dp(20), dp(20)); background = shape(Color.WHITE)
        parent.put(this, 14)
    }
    private fun field(value: String, hintText: String, multiline: Boolean = false) = EditText(host).apply {
        setText(value); hint = hintText; textSize = 15f; setTextColor(ink); setHintTextColor(muted)
        background = shape(canvas, 12); backgroundTintList = null
        setPadding(dp(14), dp(12), dp(14), dp(12))
        inputType = if (multiline) android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE
            else android.text.InputType.TYPE_CLASS_TEXT
        if (multiline) { minLines = 3; gravity = android.view.Gravity.TOP } else setSingleLine(true)
    }
    private fun button(label: String, key: String, primary: Boolean = false): Button = Button(host).apply {
        text = label; textSize = 15f; isAllCaps = false
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        setTextColor(if (primary) Color.WHITE else teal)
        background = touchBackground(if (primary) teal else Color.rgb(234, 244, 242))
        backgroundTintList = null; minHeight = dp(50); minimumHeight = dp(50)
        stateListAnimator = null
        setPadding(dp(12), dp(10), dp(12), dp(10))
        setOnClickListener { action(key) }
    }
    private fun disclosure(parent: LinearLayout, title: String, subtitle: String): LinearLayout {
        val outer = card(parent)
        val heading = text("+  " + title, 17f, ink, true)
        heading.minHeight = dp(42); heading.gravity = android.view.Gravity.CENTER_VERTICAL
        outer.put(heading); outer.put(text(subtitle, 12f, muted), 2)
        val content = column().apply { visibility = View.GONE }
        outer.put(content, 8)
        heading.contentDescription = title + "，点击展开或收起"
        heading.setOnClickListener {
            val expanded = content.visibility != View.VISIBLE
            content.visibility = if (expanded) View.VISIBLE else View.GONE
            heading.text = (if (expanded) "−  " else "+  ") + title
        }
        return content
    }
    private val page = column().apply { setPadding(dp(18), dp(16), dp(18), dp(28)) }
    val status = text("正在初始化…", 13f, teal).apply {
        background = shape(Color.rgb(229, 243, 238), 12)
        setPadding(dp(14), dp(12), dp(14), dp(12))
        accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
    }
    val points = field("调查居民需求\n组织分层宣传\n评估宣传效果", "每行填写一个参考要点", true)
    val mode = Spinner(host)
    val server = field("http://192.168.1.2:8000", "电脑服务地址")
    val token = field("", "实验访问凭据").apply { inputType = 129 }
    val experiment = text("普通模式 · 不计入正式实验", 13f, muted)
    val samples = Spinner(host)
    val display = text("完成一段回答后，在这里查看转写与分析。", 16f).apply { setTextIsSelectable(true) }
    val timings = text("暂无运行记录", 13f, muted).apply { setTextIsSelectable(true) }
    private val modeCaption = text("手机本地分析", 12f, teal, true)
    private val coverage = column()
    private var reference = emptyMap<String, String>()
    private var shownTask: String? = null
    private lateinit var resultCard: LinearLayout
    private lateinit var scroll: ScrollView
    private val recordButton = button("开始录音", "录音 / 停止并分析", true)
    private val clock = text("最长 60 秒 · 停止后自动分析", 12f, muted)
    private val pulse = object : Runnable {
        override fun run() {
            if (!recording) return
            val seconds = (android.os.SystemClock.elapsedRealtime() - started) / 1000
            clock.text = "正在录音  %02d:%02d · 请在 60 秒内停止".format(seconds / 60, seconds % 60)
            handler.postDelayed(this, 1000)
        }
    }
    init {
        host.window.statusBarColor = canvas; host.window.navigationBarColor = canvas
        host.window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        page.put(text("VOICE / 语音练习", 11f, teal, true))
        page.put(text("让每次回答\n都有清晰反馈", 28f, ink, true), 8)
        page.put(text("录下回答，查看转写与参考要点的覆盖情况。", 13f, muted), 8)
        page.put(status, 18)
        val capture = card(page)
        capture.put(text("01  录下你的回答", 18f, ink, true))
        capture.put(text("先确认下方参考要点，再开始录音。", 13f, muted), 6)
        capture.put(modeCaption, 10)
        capture.put(recordButton, 18); capture.put(clock, 10)
        capture.put(button("选择 WAV 文件分析", "导入 WAV 并分析"), 14)
        capture.put(button("取消当前分析", "取消当前任务"), 8)
        val reference = card(page)
        reference.put(text("参考要点", 17f, ink, true))
        reference.put(text("每行一个要点，用于与回答进行语义匹配。", 12f, muted), 4)
        reference.put(points, 12)
        val result = card(page)
        resultCard = result
        result.put(text("02  回答分析", 18f, ink, true))
        result.put(text("语音转写", 12f, muted, true), 16); result.put(display, 8)
        result.put(coverage, 16)
        result.put(button("导出最近录音 WAV", "导出最近 WAV"), 16)
        val execution = disclosure(page, "运行方式", "默认手机本地运行；远程与混合模式需要电脑服务。")
        execution.put(mode)
        val remoteFields = column().apply { put(text("电脑服务地址", 12f, muted), 12); put(server, 6); put(token, 10) }
        execution.put(remoteFields)
        mode.adapter = object : ArrayAdapter<String>(host, android.R.layout.simple_spinner_item, PlanMode.values().map { it.name }) {
            private val names = listOf("手机本地 · LOCAL", "电脑远程 · REMOTE", "手动混合 · MANUAL_MIXED")
            override fun getView(position: Int, recycled: View?, parent: android.view.ViewGroup): View =
                super.getView(position, recycled, parent).also { (it as TextView).text = names[position]; it.setTextColor(ink); it.textSize = 15f }
            override fun getDropDownView(position: Int, recycled: View?, parent: android.view.ViewGroup): View =
                super.getDropDownView(position, recycled, parent).also { (it as TextView).text = names[position]; it.setPadding(dp(12), dp(14), dp(12), dp(14)) }
        }.apply { setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item) }
        mode.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) {}
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                remoteFields.visibility = if (position == 0) View.GONE else View.VISIBLE
                modeCaption.text = listOf("手机本地分析", "电脑远程分析", "手机与电脑混合分析")[position]
            }
        }
        val models = disclosure(page, "模型管理", "首次使用导入模型包；更新应用时无需重复导入。")
        models.put(button("导入模型包 ZIP", "导入模型包 ZIP"), 8)
        models.put(button("导出设备与模型信息", "导出本机及模型信息 JSON"), 8)
        val lab = disclosure(page, "实验工具", "正式测试时使用运行配置与已登记样本。")
        lab.put(experiment, 6); lab.put(samples, 12)
        listOf("导入运行配置 JSON", "导入样本清单 JSON", "退出实验模式", "导出完整实验记录 ZIP", "导出实验事件 JSONL").forEach {
            lab.put(button(it, it), 8)
        }
        val details = disclosure(page, "节点耗时与任务详情", "查看执行位置、节点耗时和任务编号。")
        details.put(timings, 8)
        page.put(text("语音回答反馈  ·  v" + com.example.interviewfeedback.BuildConfig.VERSION_NAME, 11f, muted), 22)
        scroll = ScrollView(host).apply { isFillViewport = true; setBackgroundColor(canvas); addView(page) }
        host.setContentView(scroll)
    }
    fun setRecording(value: Boolean) {
        recording = value; handler.removeCallbacks(pulse)
        recordButton.text = if (value) "停止录音并分析" else "开始录音"
        recordButton.background = touchBackground(if (value) Color.rgb(173, 58, 56) else teal)
        if (value) { started = android.os.SystemClock.elapsedRealtime(); handler.post(pulse) }
        else clock.text = "最长 60 秒 · 停止后自动分析"
    }
    fun setReference(points: List<Keypoint>) { reference = points.associate { it.id to it.text } }
    fun clearFeedback() { coverage.removeAllViews(); display.text = "正在处理录音，首次加载模型可能需要稍等。" }
    fun render(record: TaskRecord) {
        val labels = mapOf(TaskStatus.CREATED to "准备分析", TaskStatus.RUNNING to "正在分析，请稍候", TaskStatus.SUCCEEDED to "分析完成", TaskStatus.FAILED to "分析失败", TaskStatus.CANCELLED to "已取消", TaskStatus.INTERRUPTED to "任务已中断")
        status.text = labels[record.status] + (record.error?.let { " · " + it.name } ?: "")
        coverage.removeAllViews()
        val feedback = record.feedback ?: return
        display.text = feedback.transcript.fullText
        val covered = feedback.matches.values.count { it.covered }
        coverage.put(text("要点覆盖  $covered / ${feedback.matches.values.size}", 16f, ink, true))
        val elapsed = record.feedbackElapsedMs ?: record.totalElapsedMs
        if (elapsed != null) coverage.put(text((if (record.feedbackElapsedMs != null) "完整反馈 " else "结果生成 ") + "%.2f 秒".format(elapsed / 1000.0), 12f, muted), 4)
        feedback.matches.values.forEach { match ->
            val tint = if (match.covered) teal else Color.rgb(153, 98, 23)
            val block = column().apply {
                setPadding(dp(14), dp(14), dp(14), dp(14))
                background = shape(if (match.covered) Color.rgb(237, 247, 243) else Color.rgb(255, 247, 231), 12)
            }
            val title = reference[match.keypointId] ?: match.keypointId
            block.put(text((if (match.covered) "已覆盖  ·  " else "可能遗漏  ·  ") + title, 14f, tint, true))
            block.put(text("语义相似度  " + "%.3f".format(match.score), 12f, muted), 5)
            block.put(text("依据：" + match.evidenceText, 13f, ink), 8)
            coverage.put(block, 10)
        }
        coverage.put(text("相似度用于辅助判断，不代表回答得分。", 11f, muted), 10)
        if (shownTask != record.taskId) {
            shownTask = record.taskId
            scroll.scrollTo(0, (resultCard.top - dp(16)).coerceAtLeast(0))
        }
    }
    fun close() { recording = false; handler.removeCallbacks(pulse) }
}
