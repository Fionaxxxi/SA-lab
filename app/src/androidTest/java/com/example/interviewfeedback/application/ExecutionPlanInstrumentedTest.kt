package com.example.interviewfeedback.application

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith

/**
 * 三模式归属在真机 Runtime 上的契约验证。
 * 与 S3 报告第 2 节的归属表一一对应：M0/M5 恒 LOCAL，M1–M4 依模式分配。
 */
@RunWith(AndroidJUnit4::class)
class ExecutionPlanInstrumentedTest {

    private val eligible = setOf(Module.M1, Module.M2, Module.M3, Module.M4)

    private fun plan(mode: PlanMode, remote: Set<Module> = emptySet()) = ExecutionPlan(
        planVersion = "plan-androidtest",
        deviceId = "ELI-AN00",
        modelVersion = "modelset-e8f8c211226b-066409f3d9db-9ba59cbaae79",
        configVersion = "rules-v2",
        mode = mode,
        remote = remote,
    )

    @Test
    fun localKeepsEveryModuleOnDevice() {
        val p = plan(PlanMode.LOCAL)
        for (module in Module.values()) {
            assertEquals("LOCAL 模式下 $module 必须在本地", Executor.LOCAL, p.executor(module))
        }
    }

    @Test
    fun remoteMovesOnlyTheFourAlgorithmModules() {
        val p = plan(PlanMode.REMOTE, eligible)
        for (module in eligible) {
            assertEquals("REMOTE 模式下 $module 应在电脑执行", Executor.REMOTE, p.executor(module))
        }
        assertEquals(Executor.LOCAL, p.executor(Module.M0))
        assertEquals(Executor.LOCAL, p.executor(Module.M5))
    }

    @Test
    fun manualMixedMatchesTheS3ReportedAssignment() {
        val p = plan(PlanMode.MANUAL_MIXED, setOf(Module.M2, Module.M3))
        assertEquals(Executor.LOCAL, p.executor(Module.M0))
        assertEquals(Executor.LOCAL, p.executor(Module.M1))
        assertEquals(Executor.REMOTE, p.executor(Module.M2))
        assertEquals(Executor.REMOTE, p.executor(Module.M3))
        assertEquals(Executor.LOCAL, p.executor(Module.M4))
        assertEquals(Executor.LOCAL, p.executor(Module.M5))
    }

    @Test
    fun localRejectsAnyRemoteModule() {
        assertThrows(IllegalArgumentException::class.java) {
            plan(PlanMode.LOCAL, setOf(Module.M2))
        }
    }

    @Test
    fun remoteRejectsAPartialRemoteSet() {
        assertThrows(IllegalArgumentException::class.java) {
            plan(PlanMode.REMOTE, setOf(Module.M1))
        }
    }

    @Test
    fun manualMixedRejectsBothExtremes() {
        assertThrows(IllegalArgumentException::class.java) {
            plan(PlanMode.MANUAL_MIXED, emptySet())
        }
        assertThrows(IllegalArgumentException::class.java) {
            plan(PlanMode.MANUAL_MIXED, eligible)
        }
    }

    @Test
    fun planIdentityRejectsBytesOutsideTheContract() {
        assertThrows(IllegalArgumentException::class.java) {
            ExecutionPlan(
                planVersion = "bad plan",
                deviceId = "ELI-AN00",
                modelVersion = "m",
                configVersion = "c",
                mode = PlanMode.LOCAL,
            )
        }
    }
}
