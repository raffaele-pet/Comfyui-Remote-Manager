"""Resolve Windows folders for the current installation user at runtime."""

import ctypes
import os
import uuid
from ctypes import wintypes
from pathlib import Path


def _known_folder(identifier, environment_names):
    if os.name == "nt":
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
        guid = GUID.from_buffer_copy(uuid.UUID(identifier).bytes_le)
        result = ctypes.c_wchar_p()
        get_folder = ctypes.windll.shell32.SHGetKnownFolderPath
        get_folder.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                               ctypes.POINTER(ctypes.c_wchar_p)]
        get_folder.restype = ctypes.c_long
        if get_folder(ctypes.byref(guid), 0, None, ctypes.byref(result)) == 0:
            try:
                return Path(result.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                ctypes.windll.ole32.CoTaskMemFree.restype = None
                ctypes.windll.ole32.CoTaskMemFree(result)
    for name in environment_names:
        value = os.environ.get(name)
        if value and Path(value).is_absolute():
            return Path(value)
    raise RuntimeError("Impossibile trovare una cartella di sistema Windows.")


def local_app_data_directory():
    return _known_folder("F1B32785-6FBA-4FCF-9D55-7B8E7F157091", ("LOCALAPPDATA",))


def program_files_directory():
    return _known_folder("905E63B6-C1BF-494E-B29C-65B732D3D21A", ("ProgramW6432", "ProgramFiles"))


def program_data_directory():
    return _known_folder("62AB5D82-FDC1-4DC3-A9DD-070D1D495D97", ("PROGRAMDATA",))


def desktop_directory():
    return _known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", ())
