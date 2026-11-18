# PyInstaller spec - one-folder, windowed build.
#   py -m PyInstaller VideoMetadataReporter.spec --noconfirm
# Output: dist/VideoMetadataReporter/  (zip that folder to distribute)
from PyInstaller.utils.hooks import collect_data_files

# The app uses only our own MediaInfo.dll (vendor/mediainfo, version in its VERSION file). Leave out the
# older copy that pymediainfo's wheel carries, so it can't be loaded by mistake.
datas = [d for d in collect_data_files("pymediainfo") if not d[0].lower().endswith((".dll", ".dylib", ".so"))]
binaries = []
datas += [("vendor/mediainfo", "vendor/mediainfo")]

a = Analysis(
    ["VideoMetadataReporter.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["mediareport.job", "mediareport.scanner", "mediareport.excel"],
    excludes=["PIL", "pytest", "unittest"],
)
# pymediainfo's PyInstaller hook adds its bundled MediaInfo library on its own; drop it again.
a.binaries = [b for b in a.binaries
              if not (b[0].replace("\\", "/").lower().startswith("pymediainfo/")
                      and b[0].lower().endswith((".dll", ".dylib", ".so")))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VideoMetadataReporter",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="VideoMetadataReporter")
