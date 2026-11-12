# 包名定稿决策（待三人确认）

- 状态：待确认（代码仍为占位包名）
- 日期：2026-11-12

## 现状

`mobile/app/build.gradle.kts` 中：

```kotlin
android { namespace = "com.example.interviewfeedback" }
defaultConfig { applicationId = "com.example.interviewfeedback" }
```

`mobile/README.md` 自己写明："当前 `com.example.interviewfeedback` 为目录占位。"

`com.example` 是 Android 官方示例保留前缀，商店与提交材料里出现会被视为未定稿；课程验收记录、报告封面、APK 文件名都会带上它。

## 影响面（已实测统计）

| 对象 | 数量/位置 | 说明 |
|---|---|---|
| Kotlin 源文件 | **18 个** | 每个文件都有 `package com.example.interviewfeedback...` |
| 源文件所在目录 | 2 棵 | `app/src/main/java/com/example/interviewfeedback/`、`app/src/test/java/com/example/interviewfeedback/` |
| `build.gradle.kts` | 2 处 | `namespace`、`applicationId` |
| `AndroidManifest.xml` | 0 处直接命中 | 但 `android:name=".ui.MainActivity"` 是相对名，由 namespace 解析 |
| JNI 库名 | 不受影响 | `System.loadLibrary("interview_tokenizer")` 用库名，不绑包名 |

关键点：Manifest 里 Activity 用相对类名，所以**改包名必须连同目录一起移动**，否则 `.ui.MainActivity` 会指向不存在的类。

## 候选

| 候选 | 优点 | 缺点 |
|---|---|---|
| `com.g4.interviewfeedback` | 短、与小组编号一致、无机构归属争议 | 过于通用，同名概率不为零 |
| `edu.scut.g4.interviewfeedback` | 语义清晰、带机构 | 课程作业用学校域名需谨慎，非学校官方发布物 |
| 保持 `com.example.interviewfeedback` | 零改动 | 报告与验收记录里永远是"占位"，评审会扣"未定稿" |

**建议**：`com.g4.interviewfeedback`。理由是与现有目录命名（G4 小组）一致，且不牵扯机构域名授权。

## 确认后的执行步骤

1. 建临时分支，避免污染主分支。
2. 批量替换 18 个 `.kt` 的 package 声明与 import。
3. 移动源文件目录：
   - `app/src/main/java/com/example/interviewfeedback/` → `app/src/main/java/com/g4/interviewfeedback/`
   - `app/src/test/java/com/example/interviewfeedback/` → 同理
4. 改 `build.gradle.kts` 的 `namespace` 与 `applicationId`。
5. **必须由具备 NDK 26.1.10909125 + CMake 3.22.1 的机器执行一次 `gradlew assembleDebug`**，确认 JNI 与 Manifest 解析都通过。

## 为什么现在不直接改

当前机器没有 NDK 与 CMake（`D:\Android\Sdk` 下无 `ndk`、无 `cmake` 目录），改完无法本地构建验证。包名改动会触及全部源文件路径，属于"改了但无法验证"的高风险操作，应由能构建的人执行或在补充 NDK 后执行。

## 待办

- [ ] 三人确认最终包名
- [ ] 有 NDK 的环境执行改动并构建
- [ ] 更新 `mobile/README.md`，删除"目录占位"表述
- [ ] 更新验收记录中的包名与 APK 文件名
