plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.example.interviewfeedback"
    buildFeatures { buildConfig = true }
    compileSdk = 34
    lint {
        // Course APK is sideloaded with the existing target 31 contract, not published to Play.
        // Keep Android API compatibility checks enabled; omit only the Play release policy gate.
        disable += "ExpiredTargetSdkVersion"
    }
    ndkVersion = "26.1.10909125"
    externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "3.22.1" } }
    defaultConfig {
        applicationId = "com.example.interviewfeedback"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        minSdk = 26
        targetSdk = 31
        versionCode = 4
        versionName = "0.3.0"
        buildConfigField("String", "SOURCE_REVISION", "\"" + providers.gradleProperty("sourceRevision").getOrElse("UNVERSIONED") + "\"")
        ndk { abiFilters += "arm64-v8a" }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test:runner:1.5.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.alphacephei:vosk-android:0.3.47")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
}
