//go:build windows

package main

import (
	"runtime"
	"strings"
	"syscall"
	"unsafe"
)

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	gdi32    = syscall.NewLazyDLL("gdi32.dll")

	pRegisterClassExW = user32.NewProc("RegisterClassExW")
	pCreateWindowExW  = user32.NewProc("CreateWindowExW")
	pDefWindowProcW   = user32.NewProc("DefWindowProcW")
	pGetMessageW      = user32.NewProc("GetMessageW")
	pTranslateMessage = user32.NewProc("TranslateMessage")
	pDispatchMessageW = user32.NewProc("DispatchMessageW")
	pPostMessageW     = user32.NewProc("PostMessageW")
	pGetSystemMetrics = user32.NewProc("GetSystemMetrics")
	pSendMessageW     = user32.NewProc("SendMessageW")
	pMessageBoxW      = user32.NewProc("MessageBoxW")
	pLoadCursorW      = user32.NewProc("LoadCursorW")
	pUpdateWindow     = user32.NewProc("UpdateWindow")
	pGetModuleHandleW = kernel32.NewProc("GetModuleHandleW")
	pGetStockObject   = gdi32.NewProc("GetStockObject")
)

type wndClassEx struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

const (
	wsPopup      = 0x80000000
	wsVisible    = 0x10000000
	wsBorder     = 0x00800000
	wsChild      = 0x40000000
	wsExTopmost  = 0x00000008
	wsExToolWin  = 0x00000080
	ssCenter     = 0x00000001
	wmSetFont    = 0x0030
	wmClose      = 0x0010
	colorWindow  = 5
	defaultGUI   = 17
	idcWait      = 32514
	mbIconError  = 0x00000010
)

func u16(s string) *uint16 { p, _ := syscall.UTF16PtrFromString(s); return p }

func crlf(s string) string { return strings.ReplaceAll(s, "\n", "\r\n") }

// showSplash opens a small "Setting up" window on its own thread and returns
// a function that closes it.
func showSplash(text string) func() {
	ready := make(chan uintptr, 1)
	go func() {
		runtime.LockOSThread()
		inst, _, _ := pGetModuleHandleW.Call(0)
		cursor, _, _ := pLoadCursorW.Call(0, idcWait)
		cls := u16("CORBELscoreSetup")
		wc := wndClassEx{lpfnWndProc: pDefWindowProcW.Addr(), hInstance: inst, hCursor: cursor, hbrBackground: colorWindow + 1, lpszClassName: cls}
		wc.cbSize = uint32(unsafe.Sizeof(wc))
		pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc)))
		const w, h = 380, 120
		sw, _, _ := pGetSystemMetrics.Call(0)
		sh, _, _ := pGetSystemMetrics.Call(1)
		hwnd, _, _ := pCreateWindowExW.Call(wsExTopmost|wsExToolWin, uintptr(unsafe.Pointer(cls)), uintptr(unsafe.Pointer(u16("CORBELscore"))),
			wsPopup|wsVisible|wsBorder, (sw-w)/2, (sh-h)/2, w, h, 0, 0, inst, 0)
		if hwnd == 0 {
			ready <- 0
			return
		}
		label, _, _ := pCreateWindowExW.Call(0, uintptr(unsafe.Pointer(u16("STATIC"))), uintptr(unsafe.Pointer(u16(crlf(text)))),
			wsChild|wsVisible|ssCenter, 10, 36, w-20, h-50, hwnd, 0, inst, 0)
		font, _, _ := pGetStockObject.Call(defaultGUI)
		pSendMessageW.Call(label, wmSetFont, font, 1)
		pUpdateWindow.Call(hwnd)
		ready <- hwnd
		var msg [64]byte
		for {
			r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&msg[0])), 0, 0, 0)
			if r == 0 || int32(r) == -1 {
				return
			}
			pTranslateMessage.Call(uintptr(unsafe.Pointer(&msg[0])))
			pDispatchMessageW.Call(uintptr(unsafe.Pointer(&msg[0])))
		}
	}()
	hwnd := <-ready
	return func() {
		if hwnd != 0 {
			pPostMessageW.Call(hwnd, wmClose, 0, 0)
		}
	}
}

func fail(text string) {
	pMessageBoxW.Call(0, uintptr(unsafe.Pointer(u16(crlf(text)))), uintptr(unsafe.Pointer(u16("CORBELscore"))), mbIconError)
}
