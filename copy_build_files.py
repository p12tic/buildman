#!/usr/bin/env python3

import os
import os.path
import sys
import re
import fnmatch
import shutil
import time

if len(sys.argv) < 1:
    print("Bad arguments")
    sys.exit(1)

target_path = os.getcwd()
sys.argv.pop(0)
src_path = sys.argv[0]

if re.search(r'kicad', target_path):
    target_path += '/build/kicad'
elif re.search(r'qtcreator', target_path):
    target_path += '/builddir'
elif re.search(r'libwnckmm', target_path):
    target_path += '/build'
elif re.search(r'emerald', target_path):
    pass
else:
    sys.exit(0)

print("Copying from: " + target_path)
print("Coping to:    " + src_path)

obj_matches = []
dep_matches = []
dir_matches = []
for root, dirnames, filenames in os.walk(src_path):
    root = root.replace(src_path, "", 1)  # relative path
    root = root.lstrip('/')
    for fn in fnmatch.filter(filenames, '*.o'):
        obj_matches.append(os.path.join(root, fn))
    for fn in fnmatch.filter(filenames, '*.lo'):
        obj_matches.append(os.path.join(root, fn))
    for fn in fnmatch.filter(filenames, '*.Plo'):
        dep_matches.append(os.path.join(root, fn))
    for dirc in dirnames:
        dir_matches.append(os.path.join(root, dirc))

# create .dirstamp files
for dirc in dir_matches:
    dirc = os.path.join(target_path, dirc)
    try:
        os.makedirs(dirc)
    except Exception:
        pass
    # open(os.path.join(dirc, '.dirstamp'), 'a').close()

# create dummy dependency files
for fn in dep_matches:
    shutil.copyfile(os.path.join(src_path, fn),
                    os.path.join(target_path, fn))
    os.utime(os.path.join(target_path, fn), (time.time() + 1040,
                                             time.time() + 1040))
# copy objects
for fn in obj_matches:
    print(fn)
    shutil.copyfile(os.path.join(src_path, fn),
                    os.path.join(target_path, fn))
    os.utime(os.path.join(target_path, fn), (time.time() + 1040,
                                             time.time() + 1040))
