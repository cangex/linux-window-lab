/* SPDX-License-Identifier: MIT
 * Userspace liveness evidence. This is not an external memory reader (P4).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static uint32_t crc32(const unsigned char *p, size_t n) {
    uint32_t crc = 0xffffffffU;
    while (n--) {
        crc ^= *p++;
        for (unsigned i=0;i<8;i++) crc=(crc>>1)^((0U-(crc&1U))&0xedb88320U);
    }
    return ~crc;
}
static LRESULT CALLBACK heartbeat_window(HWND w, UINT m, WPARAM a, LPARAM b) {
    if (m==WM_PAINT) { PAINTSTRUCT p; BeginPaint(w,&p); EndPaint(w,&p); return 0; }
    if (m==WM_ERASEBKGND) return 1;
    return DefWindowProcA(w,m,a,b);
}
static HWND make_heartbeat_window(void) {
    WNDCLASSA c={0};
    SetProcessDPIAware();
    c.lpfnWndProc=heartbeat_window; c.hInstance=GetModuleHandle(NULL);
    c.lpszClassName="LwP3Heartbeat";
    if (!RegisterClassA(&c)) return NULL;
    return CreateWindowExA(WS_EX_TOPMOST|WS_EX_TOOLWINDOW,c.lpszClassName,
        "LWLAB P3 visual heartbeat",WS_POPUP|WS_VISIBLE,0,700,512,48,
        NULL,NULL,c.hInstance,NULL);
}
static int paint_heartbeat(HWND window, uint64_t nonce, uint64_t seq, uint64_t tick) {
    unsigned char record[48]={0};
    static uint32_t pixels[512*48];
    uint32_t pid=GetCurrentProcessId(), version=1, crc, inverse;
    memcpy(record,"LWP3HB01",8); memcpy(record+8,&nonce,8);
    memcpy(record+16,&seq,8); memcpy(record+24,&tick,8);
    memcpy(record+32,&pid,4); memcpy(record+36,&version,4);
    crc=crc32(record,40); inverse=~crc;
    memcpy(record+40,&crc,4); memcpy(record+44,&inverse,4);
    for (unsigned bit=0;bit<384;bit++) {
        uint32_t color=(record[bit/8]>>(bit%8))&1 ? 0x00f0f0f0 : 0x00101010;
        for (unsigned y=0;y<8;y++) for (unsigned x=0;x<8;x++)
            pixels[((bit/64)*8+y)*512+(bit%64)*8+x]=color;
    }
    MSG msg;
    while (PeekMessage(&msg,NULL,0,0,PM_REMOVE)) { TranslateMessage(&msg); DispatchMessage(&msg); }
    BITMAPINFO info={0};
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=512; info.bmiHeader.biHeight=-48;
    info.bmiHeader.biPlanes=1; info.bmiHeader.biBitCount=32;
    info.bmiHeader.biCompression=BI_RGB;
    HDC dc=GetDC(window);
    if (!dc) return 0;
    int rows=StretchDIBits(dc,0,0,512,48,0,0,512,48,pixels,&info,DIB_RGB_COLORS,SRCCOPY);
    GdiFlush(); ReleaseDC(window,dc);
    return rows==48;
}

int main(void) {
    HWND heartbeat=make_heartbeat_window();
    if (!heartbeat) return 6;
    HANDLE serial = INVALID_HANDLE_VALUE;
    const char *port = "absent";
    const char *ports[] = {"COM2", "COM1"};
    for (unsigned i = 0; i < 2; i++) {
        char path[32];
        snprintf(path, sizeof(path), "\\\\.\\%s", ports[i]);
        serial = CreateFileA(path, GENERIC_READ | GENERIC_WRITE, 0, NULL,
                             OPEN_EXISTING, 0, NULL);
        if (serial != INVALID_HANDLE_VALUE) { port = ports[i]; break; }
        printf("LWLAB_SERIAL_OPEN port=%s error=%lu\n", ports[i], GetLastError());
    }
    FILETIME now;
    LARGE_INTEGER counter;
    DWORD sent;
    char line[256];
    unsigned long long sequence = 0;
    GetSystemTimeAsFileTime(&now);
    QueryPerformanceCounter(&counter);
    unsigned long long nonce = (((unsigned long long)now.dwHighDateTime << 32)
                               | now.dwLowDateTime) ^ counter.QuadPart;
    if (serial != INVALID_HANDLE_VALUE) {
        DCB dcb = {0};
        dcb.DCBlength = sizeof(dcb);
        if (!GetCommState(serial, &dcb)) return 2;
        dcb.BaudRate = CBR_115200; dcb.ByteSize = 8;
        dcb.Parity = NOPARITY; dcb.StopBits = ONESTOPBIT;
        dcb.fOutxCtsFlow = FALSE; dcb.fOutxDsrFlow = FALSE;
        dcb.fDtrControl = DTR_CONTROL_DISABLE;
        dcb.fRtsControl = RTS_CONTROL_DISABLE;
        dcb.fOutX = FALSE; dcb.fInX = FALSE;
        if (!SetCommState(serial, &dcb)) return 3;
        COMMTIMEOUTS timeouts = {0};
        timeouts.WriteTotalTimeoutConstant = 1000;
        if (!SetCommTimeouts(serial, &timeouts)) return 4;
    }
    for (;;) {
        unsigned long long tick=GetTickCount64();
        int length = snprintf(line, sizeof(line),
            "LWLAB_P3_USER nonce=%016llx seq=%llu pid=%lu tick=%llu serial=%s\r\n",
            nonce, sequence, GetCurrentProcessId(), tick,
            port);
        fputs(line, stdout); fflush(stdout);
        if (serial != INVALID_HANDLE_VALUE &&
            (!WriteFile(serial, line, (DWORD)length, &sent, NULL) || sent != (DWORD)length))
            return 5;
        if (!paint_heartbeat(heartbeat,nonce,sequence,tick)) return 7;
        sequence++;
        Sleep(1000);
    }
}
