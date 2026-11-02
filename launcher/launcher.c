/* Capricorn.exe - a tiny launcher so Windows shows "Capricorn" (name + icon) in the taskbar and Task
   Manager instead of "Python". It runs Python *inside this process*:
     1. find ..\pyvenv.cfg (this exe lives in capricorn-data\python\Scripts) -> the Python install ("home")
     2. load python3XX.dll from there
     3. run  -m capricorn <your arguments>  with the repo folder as the working directory
   Build (any OS):  python -m ziglang build-exe launcher.c launcher.rc -target x86_64-windows-gnu ...
   (see build.py). No Python code is embedded; it's just a launcher. */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>

typedef int (*PyMainFn)(int, wchar_t **);

static void fail(const wchar_t *msg) {
    MessageBoxW(NULL, msg, L"Capricorn", MB_ICONERROR | MB_OK);
}

static int read_cfg(const wchar_t *cfg, wchar_t *home, wchar_t *ver) {
    FILE *f = _wfopen(cfg, L"r, ccs=UTF-8");
    if (!f) return 0;
    wchar_t line[1024];
    home[0] = ver[0] = 0;
    while (fgetws(line, 1024, f)) {
        wchar_t *eq = wcschr(line, L'=');
        if (!eq) continue;
        *eq = 0;
        wchar_t *k = line, *v = eq + 1;
        while (*k == L' ') k++;
        wchar_t *ke = k + wcslen(k);
        while (ke > k && (ke[-1] == L' ' || ke[-1] == L'\t')) *--ke = 0;
        while (*v == L' ') v++;
        wchar_t *ve = v + wcslen(v);
        while (ve > v && (ve[-1] == L'\n' || ve[-1] == L'\r' || ve[-1] == L' ')) *--ve = 0;
        if (_wcsicmp(k, L"home") == 0) wcsncpy(home, v, MAX_PATH - 1);
        else if (_wcsicmp(k, L"version") == 0 || _wcsicmp(k, L"version_info") == 0) wcsncpy(ver, v, 63);
    }
    fclose(f);
    return home[0] != 0;
}

static void parent(wchar_t *p) {
    wchar_t *s = wcsrchr(p, L'\\');
    if (s) *s = 0;
}

/* Started from the repo folder (or launcher\): copy ourselves into capricorn-data\python\Scripts
   (where Python's environment lives) and run that copy - it's the one Task Manager shows. */
static int relaunch_from_repo(const wchar_t *exe, const wchar_t *dir) {
    wchar_t repo[MAX_PATH], cfg[MAX_PATH], target[MAX_PATH], tmp[4096];
    const wchar_t *tries[2] = {L"", L"\\.."};
    for (int t = 0; t < 2; t++) {
        swprintf(repo, MAX_PATH, L"%ls%ls", dir, tries[t]);
        swprintf(cfg, MAX_PATH, L"%ls\\capricorn-data\\python\\pyvenv.cfg", repo);
        if (GetFileAttributesW(cfg) == INVALID_FILE_ATTRIBUTES) continue;
        swprintf(target, MAX_PATH, L"%ls\\capricorn-data\\python\\Scripts\\Capricorn.exe", repo);
        /* refresh the copy when it's missing or a different size (ignore "in use") */
        WIN32_FILE_ATTRIBUTE_DATA a, b;
        BOOL have = GetFileAttributesExW(target, GetFileExInfoStandard, &b);
        GetFileAttributesExW(exe, GetFileExInfoStandard, &a);
        if (!have || a.nFileSizeLow != b.nFileSizeLow || CompareFileTime(&a.ftLastWriteTime, &b.ftLastWriteTime) > 0) {
            CopyFileW(exe, target, FALSE);
        }
        if (GetFileAttributesW(target) == INVALID_FILE_ATTRIBUTES) break;
        /* pass our arguments through */
        const wchar_t *cl = GetCommandLineW();
        if (*cl == L'"') { cl++; while (*cl && *cl != L'"') cl++; if (*cl) cl++; }
        else { while (*cl && *cl != L' ') cl++; }
        swprintf(tmp, 4096, L"\"%ls\"%ls", target, cl);
        STARTUPINFOW si = {sizeof(si)};
        PROCESS_INFORMATION pi;
        if (CreateProcessW(target, tmp, NULL, NULL, FALSE, 0, NULL, repo, &si, &pi)) {
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return 0;
        }
        break;
    }
    fail(L"Capricorn isn't set up yet (capricorn-data\\python not found next to Capricorn.exe).\n\n"
         L"Run setup.bat first.");
    return 1;
}

int WINAPI WinMain(HINSTANCE hi, HINSTANCE hp, LPSTR cmd, int show) {
    (void)hi; (void)hp; (void)cmd; (void)show;
    wchar_t exe[MAX_PATH], dir[MAX_PATH], cfg[MAX_PATH], home[MAX_PATH], ver[64], dll[MAX_PATH], repo[MAX_PATH];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    wcscpy(dir, exe);
    parent(dir);                                     /* ...\python\Scripts */

    swprintf(cfg, MAX_PATH, L"%ls\\pyvenv.cfg", dir);
    if (!read_cfg(cfg, home, ver)) {
        wchar_t up[MAX_PATH];
        wcscpy(up, dir);
        parent(up);
        swprintf(cfg, MAX_PATH, L"%ls\\pyvenv.cfg", up);
        if (!read_cfg(cfg, home, ver)) {
            return relaunch_from_repo(exe, dir);
        }
    }
    /* "3.12.10" -> python312.dll */
    int major = 3, minor = 12;
    swscanf(ver, L"%d.%d", &major, &minor);
    swprintf(dll, MAX_PATH, L"%ls\\python%d%d.dll", home, major, minor);

    SetDllDirectoryW(home);
    HMODULE (WINAPI *addDir)(PCWSTR) = (void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "AddDllDirectory");
    if (addDir) addDir(home);
    HMODULE py = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!py) {
        wchar_t msg[MAX_PATH + 200];
        swprintf(msg, MAX_PATH + 200, L"Couldn't load %ls\n\nIs Python still installed there? Run setup.bat again.", dll);
        fail(msg);
        return 1;
    }
    PyMainFn py_main = (PyMainFn)GetProcAddress(py, "Py_Main");
    if (!py_main) {
        fail(L"This Python has no Py_Main - run setup.bat again.");
        return 1;
    }

    /* repo folder = Scripts\..\..\.. (Scripts -> python -> capricorn-data -> repo) */
    wcscpy(repo, dir);
    parent(repo); parent(repo); parent(repo);
    SetCurrentDirectoryW(repo);

    int n = 0;
    wchar_t **args = CommandLineToArgvW(GetCommandLineW(), &n);
    wchar_t **argv = (wchar_t **)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(wchar_t *) * (n + 4));
    int c = 0;
    argv[c++] = exe;
    argv[c++] = L"-m";
    argv[c++] = L"capricorn";
    for (int i = 1; i < n; i++) argv[c++] = args[i];
    argv[c] = NULL;
    DWORD t0 = GetTickCount();
    int rc = py_main(c, argv);
    if (rc != 0 && GetTickCount() - t0 < 15000 && n <= 1) {
        fail(L"Capricorn stopped right after starting.\n\n"
             L"Run Capricorn-debug.bat to see the error, or check capricorn-data\\logs\\capricorn.log.");
    }
    return rc;
}
