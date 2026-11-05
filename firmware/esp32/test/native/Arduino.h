#pragma once
// Substitutos somente para testar o protocolo no host, sem hardware.
#include <cstdint>
#include <cstdio>
#include <string>
#include <cstdarg>
using String = std::string;
extern uint64_t testeMicros;
inline uint32_t millis() { return testeMicros / 1000; }
inline void delay(int ms) { testeMicros += ms * 1000; }
struct SerialTeste {
  std::string saida;
  std::string entrada;
  void begin(int) {}
  size_t write(uint8_t c) { saida += char(c); return 1; }
  size_t write(const uint8_t *p, size_t n) { saida.append(reinterpret_cast<const char *>(p), n); return n; }
  void println(const char *p) { saida += p; saida += '\n'; }
  void printf(const char *fmt, ...) {
    char b[512]; va_list args; va_start(args, fmt);
    vsnprintf(b, sizeof(b), fmt, args); va_end(args); saida += b;
  }
  int available() { return entrada.size(); }
  int read() { char c = entrada.front(); entrada.erase(0, 1); return c; }
};
extern SerialTeste Serial;
