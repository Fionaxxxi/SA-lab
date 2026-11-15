package com.example.interviewfeedback.analysis.semantic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EvidenceSelectionTest {

    // ---------- 最长公共子串 ----------

    @Test
    fun `overlap counts the longest contiguous run`() {
        assertEquals(6, RealModules.overlap("第三步评估宣传效果看公众号阅读量", "评估宣传效果"))
        assertEquals(2, RealModules.overlap("组织分层宣传", "评估宣传效果"))
        assertEquals(5, RealModules.overlap("老年居民靠楼栋长上门", "楼栋长上门走访"))
    }

    @Test
    fun `overlap handles identical empty and unrelated strings`() {
        val text = "调查居民需求"
        assertEquals(text.length, RealModules.overlap(text, text))
        assertEquals(0, RealModules.overlap("", text))
        assertEquals(0, RealModules.overlap(text, ""))
        assertEquals(0, RealModules.overlap("abc", "xyz"))
    }

    @Test
    fun `overlap keeps characters in order rather than counting them`() {
        // 「宣」与「传」在两串里都有，但不连续，只能取 1。
        assertEquals(1, RealModules.overlap("宣传", "传宣"))
    }

    // ---------- 依据选句 ----------

    @Test
    fun `evidence picks the longer shared run inside the score band`() {
        // 第 6 次真机实测：s5 短句分数更高（0.7678），s10 长句更贴切（0.7243）。
        val texts = listOf(
            "组织分层宣传",
            "第三步评估宣传效果看公众号阅读量抽样知晓率和参与人数变化"
        )
        val scores = listOf(0.7678, 0.7243)
        assertEquals(1, RealModules.chooseEvidence(scores, texts, listOf(0, 1), "评估宣传效果"))
    }

    @Test
    fun `evidence picks the longer shared run on the seventh recording`() {
        // 第 7 次真机实测：s6 0.6835（LCS 2）、s12 0.6721（LCS 6）。
        val texts = listOf(
            "组织分层宣传",
            "第三步评估宣传效果看公众号阅读量抽样知晓率和参与人数变化"
        )
        val scores = listOf(0.6835, 0.6721)
        assertEquals(1, RealModules.chooseEvidence(scores, texts, listOf(0, 1), "评估宣传效果"))
    }

    @Test
    fun `evidence falls back to the top sentence when the gap exceeds the band`() {
        // 0.30 远低于 0.90 × 0.85，即使重合更长也不能顶掉最高分句。
        val texts = listOf("组织分层宣传", "第三步评估宣传效果看公众号阅读量")
        val scores = listOf(0.90, 0.30)
        assertEquals(0, RealModules.chooseEvidence(scores, texts, listOf(0, 1), "评估宣传效果"))
    }

    @Test
    fun `evidence falls back to the top sentence when every candidate shares too little`() {
        // 两句话与要点都没有 2 字以上的连续重合，退回最高分句。
        val texts = listOf("组织分层宣传", "入户走访和问卷")
        val scores = listOf(0.90, 0.88)
        assertEquals(0, RealModules.chooseEvidence(scores, texts, listOf(0, 1), "评估宣传效果"))
    }

    @Test
    fun `evidence prefers the higher score when the shared run ties`() {
        val texts = listOf("先调查居民需求", "再调查居民需求")
        val scores = listOf(0.80, 0.90)
        assertEquals(1, RealModules.chooseEvidence(scores, texts, listOf(0, 1), "调查居民需求"))
    }

    @Test
    fun `evidence never changes which sentence supplies the score`() {
        // 选中 s10 作依据，但分数必须仍来自 s5，这是「分值零偏移」的代码层保证。
        val texts = listOf("组织分层宣传", "第三步评估宣传效果看公众号阅读量")
        val scores = listOf(0.7678, 0.7243)
        val pool = listOf(0, 1)
        val evidence = RealModules.chooseEvidence(scores, texts, pool, "评估宣传效果")
        val best = pool.maxBy { scores[it] }
        assertEquals(1, evidence)
        assertEquals(0, best)
        assertEquals(0.7678, scores[best], 0.0)
    }

    // ---------- 覆盖判定 ----------

    @Test
    fun `negated top sentence is never counted as covered`() {
        // S25 k4 真机实测：分数 0.8941，原句含「不再收集反馈」，必须判未覆盖。
        val top = "不过为了省事操作时让志愿者统一收集密码和验证码当然就不再收集反馈和提供帮助渠道"
        assertFalse(RealModules.isCovered(0.8941, 0.54, true, top))
    }

    @Test
    fun `plain sentence above the threshold is covered`() {
        val top = "第三步评估宣传效果看公众号阅读量抽样知晓率和参与人数变化"
        assertTrue(RealModules.isCovered(0.845, 0.54, true, top))
    }

    @Test
    fun `score below the threshold is not covered`() {
        val top = "第三步评估宣传效果看公众号阅读量"
        assertFalse(RealModules.isCovered(0.439, 0.54, true, top))
    }

    @Test
    fun `sentence excluded by the clause-level negation filter is not covered`() {
        val top = "调查居民需求"
        assertFalse(RealModules.isCovered(0.9, 0.54, false, top))
    }

    // ---------- 否定正则 ----------

    @Test
    fun `negated evidence catches the six writing patterns measured on device`() {
        val hit = listOf(
            // 「不再 + 动词」5 句
            "不再收集反馈和提供帮助渠道",
            "办完就不再收集反馈或提供帮助渠道",
            "不再提供帮助",
            "不再监测后续情况",
            "我不再回访居民",
            // 「没有 / 未 / 不 + 动词」各 1 句
            "没有设置警戒线",
            "未安排疏散",
            "不组织案例宣传",
            "先观察高峰时段不调整方案",
            // 原有 8 句
            "不打算提醒居民保护验证码",
            "也不准备讲转账核实",
            "不做反馈和回访",
            "无需再监测",
            "我不准备封闭危险区域或疏散居民",
            "不会调整桶点",
            "也不会记录错误投放",
            "我不打算提醒居民,也不准备讲转账"
        )
        assertEquals(17, hit.size)
        hit.forEach { sentence ->
            val matched = RealModules.NEGATED_EVIDENCE.containsMatchIn(sentence)
            assertTrue("应当命中否定表：$sentence", matched)
        }
    }

    @Test
    fun `negated evidence leaves ordinary sentences alone`() {
        val miss = listOf(
            "不了解情况的先登记",
            "未来三天每天巡查一次",
            "不要忘记登记来访信息",
            "不断改进分层宣传方式"
        )
        miss.forEach { sentence ->
            val matched = RealModules.NEGATED_EVIDENCE.containsMatchIn(sentence)
            assertFalse("不应误判为否定句：$sentence", matched)
        }
    }

    @Test
    fun `verb list deliberately excludes the word liaojie`() {
        // 「了解」若留在动词表，「不了解情况」会被当成「不做了解」，这是实测踩过的坑。
        assertFalse("了解" in RealModules.NEGATED_VERB)
        assertFalse(RealModules.NEGATED_EVIDENCE.containsMatchIn("不了解情况的先登记"))
    }

    // ---------- 常量 ----------

    @Test
    fun `evidence band and minimum overlap match the documented values`() {
        assertEquals(0.85, RealModules.EVIDENCE_BAND, 0.0)
        assertEquals(2, RealModules.EVIDENCE_MIN_OVERLAP)
    }
}
