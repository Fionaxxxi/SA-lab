#include <jni.h>
#include <sentencepiece_processor.h>
#include <cstdint>
#include <string>
#include <vector>

using sentencepiece::SentencePieceProcessor;
extern "C" JNIEXPORT jlong JNICALL
Java_com_example_interviewfeedback_analysis_semantic_SentencePiece_open(JNIEnv* env, jobject, jstring path) {
    const char* value = env->GetStringUTFChars(path, nullptr);
    auto* processor = new SentencePieceProcessor();
    auto status = processor->Load(value);
    env->ReleaseStringUTFChars(path, value);
    if (!status.ok()) { delete processor; return 0; }
    return reinterpret_cast<jlong>(processor);
}
extern "C" JNIEXPORT jintArray JNICALL
Java_com_example_interviewfeedback_analysis_semantic_SentencePiece_encodeNative(JNIEnv* env, jobject, jlong handle, jstring text) {
    // Java UTF-16 is converted by Java to standard UTF-8 before entering SentencePiece.
    jclass stringClass = env->FindClass("java/lang/String");
    jmethodID getBytes = env->GetMethodID(stringClass, "getBytes", "(Ljava/lang/String;)[B");
    jstring encoding = env->NewStringUTF("UTF-8");
    auto bytes = static_cast<jbyteArray>(env->CallObjectMethod(text, getBytes, encoding));
    jsize size = env->GetArrayLength(bytes);
    jbyte* raw = env->GetByteArrayElements(bytes, nullptr);
    std::string utf8(reinterpret_cast<char*>(raw), size);
    env->ReleaseByteArrayElements(bytes, raw, JNI_ABORT);
    auto* processor = reinterpret_cast<SentencePieceProcessor*>(handle);
    std::vector<int> ids;
    auto status = processor->Encode(utf8, &ids);
    if (!status.ok()) {
        env->ThrowNew(env->FindClass("java/lang/IllegalArgumentException"), "SentencePiece encoding failed");
        return nullptr;
    }
    jintArray result = env->NewIntArray(ids.size());
    env->SetIntArrayRegion(result, 0, ids.size(), ids.data());
    return result;
}
extern "C" JNIEXPORT void JNICALL
Java_com_example_interviewfeedback_analysis_semantic_SentencePiece_destroy(JNIEnv*, jobject, jlong handle) {
    delete reinterpret_cast<SentencePieceProcessor*>(handle);
}
