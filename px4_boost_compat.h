// glibc 2.34+ 把 PTHREAD_STACK_MIN 从常量改为函数调用，
// Boost 1.71 的 #if PTHREAD_STACK_MIN > 0 在预处理阶段无法求值。
// 本文件仅在编译 sitl_gazebo 时通过 -include 注入，绕过此兼容问题。
#ifdef PTHREAD_STACK_MIN
#undef PTHREAD_STACK_MIN
#endif
#define PTHREAD_STACK_MIN 16384
