# PyInstaller spec - one-folder, windowed build.
#   py -m PyInstaller VideoMetadataReporter.spec --noconfirm
# Output: dist/VideoMetadataReporter/  (zip that folder to distribute)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# pymediainfo ships the MediaInfo library (DLL / dylib) inside the wheel
datas = collect_data_files("pymediainfo")
binaries = collect_dynamic_libs("pymediainfo")
# Our own, newer MediaInfo.dll (see vendor/mediainfo/VERSION); the app prefers it over pymediainfo's.
datas += [("vendor/mediainfo", "vendor/mediainfo")]

a = Analysis(
    ["VideoMetadataReporter.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["mediareport.job", "mediareport.scanner", "mediareport.excel"],
    excludes=["PIL", "pytest", "unittest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VideoMetadataReporter",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="VideoMetadataReporter")
