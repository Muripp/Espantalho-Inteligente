#pragma once
#include <cstdint>
extern uint64_t testeMicros;
inline int64_t esp_timer_get_time() { return testeMicros; }
