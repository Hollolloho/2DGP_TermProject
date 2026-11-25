"""Keep movement keys out of text composition in the game's SDL window."""
import ctypes


def disable_text_input(p):
    p.SDL_StopTextInput()
    if p.SDL_GetCurrentVideoDriver() != b'windows':
        return
    # SDL2 stops the IME on its keyboard-focus window. At startup that
    # window can still be null while our HWND already has an input context.
    info = p.SDL_SysWMinfo()
    p.SDL_GetVersion(ctypes.byref(info.version))
    if p.SDL_GetWindowWMInfo(p.window, ctypes.byref(info)) and info.subsystem == p.SDL_SYSWM_WINDOWS:
        associate = ctypes.windll.imm32.ImmAssociateContext
        associate.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        associate.restype = ctypes.c_void_p
        associate(info.info.win.window, None)
