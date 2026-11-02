/* Setup.exe - starts the Capricorn setup wizard (installer\wizard.pyw).
   The wizard is written in Python (standard library only), so this small native program first makes sure a
   suitable Python (3.12, or 3.11 / 3.13) is installed - if not, it offers to download the official Python
   3.12 installer from python.org (~26 MB) and installs it just for this user, with no admin rights.
   "Setup.exe --uninstall" opens the wizard in uninstall mode (used by Windows Settings > Apps).
   Build: python installer/build.py  (cross-compiles with zig; no Visual Studio needed). */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <urlmon.h>
#include <stdio.h>
#include <wchar.h>

#define PY_VERSION_FULL L"3.12.10"
#define PY_URL L"https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

static const wchar_t *VERSIONS[] = {L"3.12", L"3.13", L"3.11"};
static HWND g_wnd, g_text;
static volatile LONG g_done = 0;
static volatile HRESULT g_hr = S_OK;
static wchar_t g_tmp[MAX_PATH];

static int file_exists(const wchar_t *p) { return GetFileAttributesW(p) != INVALID_FILE_ATTRIBUTES; }

/* pythonw.exe for an installed Python with tkinter, or 0 */
static int find_python(wchar_t *out) {
    HKEY roots[2] = {HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
    for (int v = 0; v < 3; v++) {
        for (int r = 0; r < 2; r++) {
            wchar_t key[128], dir[MAX_PATH];
            DWORD sz = sizeof(dir);
            swprintf(key, 128, L"Software\\Python\\PythonCore\\%ls\\InstallPath", VERSIONS[v]);
            if (RegGetValueW(roots[r], key, NULL, RRF_RT_REG_SZ, NULL, dir, &sz) == ERROR_SUCCESS) {
                size_t n = wcslen(dir);
                if (n && dir[n - 1] == L'\\') dir[n - 1] = 0;
                wchar_t tk[MAX_PATH];
                swprintf(out, MAX_PATH, L"%ls\\pythonw.exe", dir);
                swprintf(tk, MAX_PATH, L"%ls\\Lib\\tkinter\\__init__.py", dir);
                if (file_exists(out) && file_exists(tk)) return 1;
            }
        }
        /* default per-user location */
        wchar_t la[MAX_PATH], tk[MAX_PATH];
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", la, MAX_PATH)) {
            const wchar_t *d = VERSIONS[v];
            wchar_t nodot[8] = {0};
            int j = 0;
            for (int i = 0; d[i] && j < 7; i++) if (d[i] != L'.') nodot[j++] = d[i];
            swprintf(out, MAX_PATH, L"%ls\\Programs\\Python\\Python%ls\\pythonw.exe", la, nodot);
            swprintf(tk, MAX_PATH, L"%ls\\Programs\\Python\\Python%ls\\Lib\\tkinter\\__init__.py", la, nodot);
            if (file_exists(out) && file_exists(tk)) return 1;
        }
    }
    return 0;
}

static DWORD WINAPI worker(LPVOID arg) {
    (void)arg;
    SetWindowTextW(g_text, L"Downloading Python " PY_VERSION_FULL L" from python.org (about 26 MB)...");
    GetTempPathW(MAX_PATH, g_tmp);
    wcscat(g_tmp, L"capricorn-python-setup.exe");
    g_hr = URLDownloadToFileW(NULL, PY_URL, g_tmp, 0, NULL);
    if (SUCCEEDED(g_hr)) {
        SetWindowTextW(g_text, L"Installing Python " PY_VERSION_FULL L" for your user account (no admin needed)...");
        wchar_t cmd[MAX_PATH * 2];
        swprintf(cmd, MAX_PATH * 2, L"\"%ls\" /quiet InstallAllUsers=0 Include_launcher=1 InstallLauncherAllUsers=0 "
                 L"Include_tcltk=1 Include_test=0 Include_doc=0 PrependPath=0 Shortcuts=0", g_tmp);
        STARTUPINFOW si = {sizeof(si)};
        PROCESS_INFORMATION pi;
        if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
            WaitForSingleObject(pi.hProcess, INFINITE);
            DWORD code = 0;
            GetExitCodeProcess(pi.hProcess, &code);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            if (code != 0 && code != 3010) g_hr = E_FAIL;
        } else {
            g_hr = E_FAIL;
        }
        DeleteFileW(g_tmp);
    }
    InterlockedExchange(&g_done, 1);
    PostMessageW(g_wnd, WM_CLOSE, 0, 0);
    return 0;
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_CLOSE) {
        if (!g_done) return 0;                       /* can't close mid-install */
        DestroyWindow(h);
        return 0;
    }
    if (m == WM_DESTROY) { PostQuitMessage(0); return 0; }
    if (m == WM_CTLCOLORSTATIC) {
        SetTextColor((HDC)w, RGB(244, 241, 250));
        SetBkColor((HDC)w, RGB(13, 10, 20));
        static HBRUSH br = 0;
        if (!br) br = CreateSolidBrush(RGB(13, 10, 20));
        return (LRESULT)br;
    }
    return DefWindowProcW(h, m, w, l);
}

static int install_python(HINSTANCE hi) {
    INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&icc);
    WNDCLASSW wc = {0};
    wc.lpfnWndProc = wndproc;
    wc.hInstance = hi;
    wc.hbrBackground = CreateSolidBrush(RGB(13, 10, 20));
    wc.lpszClassName = L"CapricornSetupBoot";
    wc.hIcon = LoadIconW(hi, MAKEINTRESOURCEW(1));
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    RegisterClassW(&wc);
    int W = 520, H = 170;
    g_wnd = CreateWindowExW(0, wc.lpszClassName, L"Capricorn Setup", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
                            (GetSystemMetrics(SM_CXSCREEN) - W) / 2, (GetSystemMetrics(SM_CYSCREEN) - H) / 2, W, H,
                            NULL, NULL, hi, NULL);
    HFONT f = CreateFontW(-15, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    g_text = CreateWindowW(L"STATIC", L"Preparing...", WS_CHILD | WS_VISIBLE, 24, 24, W - 64, 44, g_wnd, NULL, hi, NULL);
    SendMessageW(g_text, WM_SETFONT, (WPARAM)f, TRUE);
    HWND bar = CreateWindowExW(0, PROGRESS_CLASSW, NULL, WS_CHILD | WS_VISIBLE | PBS_MARQUEE, 24, 80, W - 64, 18,
                               g_wnd, NULL, hi, NULL);
    SendMessageW(bar, PBM_SETMARQUEE, TRUE, 30);
    ShowWindow(g_wnd, SW_SHOW);
    UpdateWindow(g_wnd);
    CreateThread(NULL, 0, worker, NULL, 0, NULL);
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return SUCCEEDED(g_hr);
}

int WINAPI WinMain(HINSTANCE hi, HINSTANCE hp, LPSTR cmdline, int show) {
    (void)hp; (void)cmdline; (void)show;
    wchar_t exe[MAX_PATH], dir[MAX_PATH], wizard[MAX_PATH], py[MAX_PATH];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    wcscpy(dir, exe);
    wchar_t *s = wcsrchr(dir, L'\\');
    if (s) *s = 0;
    swprintf(wizard, MAX_PATH, L"%ls\\installer\\wizard.pyw", dir);
    if (!file_exists(wizard)) {
        MessageBoxW(NULL, L"Setup files are missing.\n\nIf you opened Setup.exe from inside the downloaded .zip, "
                    L"extract (unzip) the whole folder first - right-click the zip > Extract All - then run "
                    L"Setup.exe from the extracted folder.", L"Capricorn Setup", MB_ICONWARNING);
        return 1;
    }
    if (!find_python(py)) {
        int a = MessageBoxW(NULL,
            L"Capricorn Setup needs Python 3.12 (free, from python.org).\n\n"
            L"It isn't installed on this PC yet. Setup can download it now (about 26 MB) and install it just for "
            L"your user account - no admin rights, your other programs aren't touched (about 110 MB on disk).\n\n"
            L"Download and install Python 3.12 now?",
            L"Capricorn Setup", MB_ICONQUESTION | MB_YESNO);
        if (a != IDYES) return 1;
        if (!install_python(hi) || !find_python(py)) {
            MessageBoxW(NULL, L"Python couldn't be installed automatically.\n\nInstall Python 3.12 from "
                        L"https://www.python.org/downloads/ (tick \"tcl/tk\", which is on by default), then run "
                        L"Setup.exe again.", L"Capricorn Setup", MB_ICONERROR);
            ShellExecuteW(NULL, L"open", L"https://www.python.org/downloads/release/python-31210/", NULL, NULL, SW_SHOW);
            return 1;
        }
    }
    /* pass our own arguments (e.g. --uninstall) through */
    const wchar_t *cl = GetCommandLineW();
    if (*cl == L'"') { cl++; while (*cl && *cl != L'"') cl++; if (*cl) cl++; }
    else { while (*cl && *cl != L' ') cl++; }
    wchar_t cmd[4096];
    swprintf(cmd, 4096, L"\"%ls\" \"%ls\"%ls", py, wizard, cl);
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(py, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Couldn't start the setup wizard (Python failed to start).", L"Capricorn Setup", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
