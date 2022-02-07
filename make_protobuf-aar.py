#!/usr/bin/python3

import os
from pathlib import Path
import tempfile
import sys
import multiprocessing
import shutil
import zipfile
import json

__package_name = None  # uses src folder name if set to None
__sdk_version = 21
__license_path = Path('./LICENSE')
__dependency_names = []
__schema_version = 1
__aar_version = 1
__aar_version_name = "1.0"
__cxx_stl = "c++_shared"  # c++_shared, c++_static, none , gnu stl options are possible but not supported by newer ndks
__module_export_libs = {}  # dictionary of module names and lists of export libraries for module.json
__skip_modules = ["libprotoc"]

__package_specific_configure_options = "--enable-shared --enable-cross-compile --with-protoc=protoc --disable-maintainer-mode"

__package_version = None  # set to determine_version() in main


# how to calculate the version of the library you're compiling
def determine_version():
    with Path('./protobuf_version.bzl').open('rt') as version_file:
        version = version_file.read().split('=')[1].split("'")[1]
    while version.count('.') < 3:
        version += '.0'
    return version


def get_ndk_version():
    with (Path(os.environ['ANDROID_NDK_HOME']) / "source.properties").open('rt') as ndk_source_props:
        return ndk_source_props.read().split('Pkg.Revision')[1].split('\n')[0].split('=')[1].strip().split('.')[0]
    raise Exception("couldn't determine android ndk version\nIs $ANDROID_NDK_HOME set properly?")


__ndk_version = get_ndk_version()

__arch_codes = [("armv7a-linux-androideabi", "android.armeabi-v7a"), ("aarch64-linux-android", "android.arm64-v8a"),
                ("i686-linux-android", "android.x86"), ("x86_64-linux-android", "android.x86_64"), ]


# below this line you hopefully don't have to change if you adapt this to a different library

def gen_module_json(libary_name):
    mod_info = {"library_name": libary_name}
    if libary_name in __module_export_libs:
        mod_info['export_libraries'] = __module_export_libs[libary_name]
    return json.dumps(mod_info)


def gen_android_manifest():
    return f"""<manifest xmlns:android="http://schemas.android.com/apk/res/android" 
                package="com.android.ndk.thirdparty.{__package_name}" android:versionCode="{__aar_version}" 
                android:versionName="{__aar_version_name}">
                <uses-sdk android:minSdkVersion="{__sdk_version}" android:targetSdkVersion="{__sdk_version}"/>
                </manifest>"""


def gen_prefab_json():
    return json.dumps({"name": __package_name, "schema_version": __schema_version, "dependencies": __dependency_names,
                       "version": __package_version})


__abi_json_template = {"abi": None, "api": __sdk_version, "ndk": __ndk_version, "stl": __cxx_stl}


def gen_abi_json(abi_code):
    __abi_json_template["abi"] = abi_code[8:]
    return json.dumps(__abi_json_template)


def build_arch(ndk_abi, dest_abi_code, install_folder: Path):
    cwd = Path(os.getcwd())
    build_dir = Path(tempfile.mkdtemp())
    os.chdir(build_dir)
    dest_folder = install_folder / dest_abi_code

    exec_str = f"""
PREFIX="{dest_folder}"

export PREFIX

export PATH=$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/{ndk_abi}/bin:$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin:$PATH

export SYSROOT=$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/sysroot
export CC="{ndk_abi}{__sdk_version}-clang --sysroot $SYSROOT"
export CXX="{ndk_abi}{__sdk_version}-clang++ --sysroot $SYSROOT"

{cwd.resolve()}/configure \
--prefix="$PREFIX" \
--host={ndk_abi} \
--with-sysroot="$SYSROOT" \
{__package_specific_configure_options}

make -j {multiprocessing.cpu_count()}

make install
make clean
"""
    os.system(exec_str)
    os.chdir(cwd)
    shutil.rmtree(build_dir)
    return dest_folder


def process_lib_file(filename: str, mod_name: str, ext: str, src_folder: Path, modules_folder: Path,
                     dest_abi_code: str):
    curr_mod_folder = modules_folder / mod_name[3:]
    mkifnodir(curr_mod_folder)
    if not (curr_mod_folder / "module.json").exists():
        with (curr_mod_folder / "module.json").open('wt') as mod_json:
            if ext == '.a':
                mod_json.write("{}")
            else:
                with (curr_mod_folder / "module.json").open('wt') as mod_json:
                    mod_json.write(gen_module_json(filename))
    mkifnodir(curr_mod_folder / "libs")
    dest_folder = curr_mod_folder / "libs" / dest_abi_code
    mkifnodir(dest_folder)
    with (dest_folder / "abi.json").open('wt') as abi_json:
        abi_json.write(gen_abi_json(dest_abi_code))
    if (src_folder / "include").exists():
        shutil.copytree(src_folder / "include", dest_folder / "include")
    dest_filename = (filename if ext == '.so' else mod_name) + ext
    shutil.move(src_folder / "lib" / (filename + ext), dest_folder / (dest_filename))


def place_files(ndk_abi, dest_abi_code, src_folder: Path, aar_folder: Path):
    modules_folder = aar_folder / 'prefab' / 'modules'
    shared_lib_names = [filename.name[:-3] for filename in (src_folder / "lib").glob("*.so") if
                        filename.name[:-3] not in __skip_modules]
    static_lib_names = [(filename.name[:-2],
                         filename.name[:-2] if filename.name[:-2] not in shared_lib_names else filename.name[
                                                                                               :-2] + '-static') for
                        filename in (src_folder / "lib").glob("*.a") if filename.name[:-2] not in __skip_modules]
    for shared_name in shared_lib_names:
        process_lib_file(shared_name, shared_name, '.so', src_folder, modules_folder, dest_abi_code)

    for static_name, mod_name in static_lib_names:
        process_lib_file(static_name, mod_name, '.a', src_folder, modules_folder, dest_abi_code)


def mkifnodir(p: Path):
    if type(p) is str:
        p = Path(p)
    if p.exists(): return
    p.mkdir()


def setup_prefab_structure(aar_folder: Path):
    mkifnodir(aar_folder / 'META-INF')
    shutil.copy2(__license_path, aar_folder / 'META-INF')
    mkifnodir(aar_folder / 'prefab')
    mkifnodir(aar_folder / 'prefab' / 'modules')
    with (aar_folder / "AndroidManifest.xml").open('wt') as manifest_file:
        manifest_file.write(gen_android_manifest())
    with (aar_folder / 'prefab' / 'prefab.json').open('wt') as prefab_json_file:
        prefab_json_file.write(gen_prefab_json())


def main(argv):
    global __package_name
    global __package_version

    aar_dest_folder = Path('./')
    if '-h' in argv:
        print(f"{argv[0]} - usage\n\t{argv[0]} [-i library_src_path] [-o aar_output_path_folder_only]\n \
         \n\texample: {argv[0]} -i /tmp/protobuf -o /tmp/\n\t\tcompiles libprotobuf with source in /tmp/protobuf and creates /tmp/libprotobuf-version_number.aar")
        exit(0)
    if '-o' in argv:
        aar_dest_folder = Path(argv[argv.index('-o') + 1])
    if '-i' in argv:
        os.chdir(Path(argv[argv.index('-i') + 1]))
    else:
        os.chdir(Path(__file__).parent)
    __package_version = determine_version()
    if __package_name is None:
        __package_name = Path(os.getcwd()).name
    build_folder = Path(tempfile.mkdtemp()).resolve()
    aar_folder = Path(tempfile.mkdtemp()).resolve()
    setup_prefab_structure(aar_folder)

    for arch in __arch_codes:
        place_files(*arch, build_arch(*arch, build_folder), aar_folder)
    shutil.rmtree(build_folder)
    aar_name = f"lib{__package_name}-{__package_version}.aar"
    shutil.make_archive(aar_name, "zip", root_dir=aar_folder)
    shutil.move(aar_name + '.zip', aar_dest_folder / aar_name)
    shutil.rmtree(aar_folder)
    print(f"success!!! aar file written to {str(aar_dest_folder / aar_name)}")


if __name__ == "__main__":
    main(sys.argv)
