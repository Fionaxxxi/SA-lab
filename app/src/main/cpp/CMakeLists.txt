cmake_minimum_required(VERSION 3.22)
project(interview_tokenizer)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
include(FetchContent)
set(SPM_ENABLE_SHARED OFF CACHE BOOL "" FORCE)
set(SPM_ENABLE_TCMALLOC OFF CACHE BOOL "" FORCE)
set(SPM_BUILD_TEST OFF CACHE BOOL "" FORCE)
FetchContent_Declare(sentencepiece
    URL https://files.pythonhosted.org/packages/c9/d2/b9c7ca067c26d8ff085d252c89b5f69609ca93fb85a00ede95f4857865d4/sentencepiece-0.2.0.tar.gz
    URL_HASH SHA256=a52c19171daaf2e697dc6cbe67684e0fa341b1248966f6aebb541de654d15843
    SOURCE_SUBDIR sentencepiece)
FetchContent_MakeAvailable(sentencepiece)
# The static upstream target needs Android logging from its bundled protobuf.
target_link_libraries(sentencepiece-static INTERFACE log)
add_library(interview_tokenizer SHARED tokenizer.cpp)
target_include_directories(interview_tokenizer PRIVATE ${sentencepiece_SOURCE_DIR}/sentencepiece/src ${sentencepiece_BINARY_DIR})
target_link_libraries(interview_tokenizer sentencepiece-static)
target_compile_features(interview_tokenizer PRIVATE cxx_std_17)
