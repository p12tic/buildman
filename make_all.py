#!/usr/bin/env python3
import os
import os.path
from subprocess import call
import shutil
import re
import glob
import sys

#directory layout configuration
root_path = os.environ['HOME'] + '/code/my/'
archive_path = os.environ['HOME'] + '/downloads/apt/'

copy_build_files_path = root_path + '/../my/copy_build_files.sh'

num_processors = 2

build_path =     root_path + "build/"
build_pkg_path = root_path + "build_packaging/"
pkg_path =       root_path + "packaging/"
log_path =       root_path + "log/"

log_ext = "build_log"

project_dirs = [
    root_path + 'checkouts/',
    root_path + 'local/'
    ]

def out(s):
    sys.stdout.write(s + '\n')
    sys.stdout.flush()

def sh(cmd, cwd):
    code = call(cmd, shell=True, cwd=cwd)
    if code != 0:
        out('ERROR: Command \'' + cmd + '\' returned code ' + str(code))
        sys.exit(code)
    return code

def get_log_path(proj_name):
    global log_path
    return os.path.join(log_path, proj_name)

def get_code_path(proj_name, proj_dir):
    return proj_dir

def get_build_path(proj_name):
    global build_path
    return os.path.join(build_path, proj_name)

def get_pkg_path(proj_name):
    global pkg_path
    return os.path.join(pkg_path, proj_name)

def get_build_pkg_path(proj_name):
    global build_pkg_path
    return os.path.join(build_pkg_path, proj_name)

def get_dir_mtime(path):
    max_mtime = 0
    for dirname,subdirs,files in os.walk(path):
        if re.search('\.git', dirname):
            continue
        for fname in files:
            mtime = os.path.getmtime(os.path.join(dirname, fname))
            if mtime > max_mtime:
                max_mtime = mtime
    return max_mtime

def build(proj_name, proj_dir):
    out('Configuring project \'' + proj_name + '\'')

    #compute required paths
    log_file = get_log_path(proj_name)
    code_path = get_code_path(proj_name, proj_dir)
    build_path = get_build_path(proj_name)

    if (os.path.exists(code_path + '/configure') or
        os.path.exists(code_path + '/configure.ac')):
        #autotools project

        #get modification time of the build directory, create if it does not exist

        if os.path.isdir(build_path):
            build_mtime = os.path.getmtime(build_path)
        else:
            os.makedirs(build_path)
            build_mtime = 0.0

        ac_mtime = os.path.getmtime(code_path + '/configure.ac')
        if os.path.isfile(code_path + '/configure'):
            c_mtime = os.path.getmtime(code_path + '/configure')
        else:
            c_mtime = 0.0

        #rerun autoconf if needed
        if c_mtime < ac_mtime:
            sh('autoconf; automake', cwd=code_path)
            c_mtime = os.path.getmtime(code_path + '/configure')

        #reconfigure if needed

        if build_mtime < c_mtime:
            shutil.rmtree(build_path)
            os.makedirs(build_path)
            sh(code_path + '/configure', cwd=build_path) #log_file

        #build
        out('Building project \'' + proj_name + '\'')
        sh('make all -j' + str(num_processors), cwd=build_path) #log_file

    elif os.path.exists(code_path + '/CMakeLists.txt'):
        # cmake project

        if not os.path.isdir(build_path):
            os.makedirs(build_path)

        cmd = 'cmake \'' + code_path + '\''
        out(cmd)
        sh('cmake \"' + code_path + '\"' , cwd=build_path) #log_file

        out('Building project \'' + proj_name + '\'')
        sh('make all -j' + str(num_processors), cwd=build_path) #log_file

    elif os.path.exists(code_path + "/Makefile"):
        #simple makefile project. Rebuild everything on any update in the source tree

        #get modification time of the build directory, create if it does not exist
        if os.path.isdir(build_path):
            build_mtime = get_dir_mtime(build_path)
        else:
            os.makedirs(build_path)
            build_mtime = 0

        c_mtime = get_dir_mtime(code_path)

        if (build_mtime < c_mtime):
            out('Building project \'' + proj_name + '\'')

            shutil.rmtree(build_path)
            shutil.copytree(code_path, build_path)

            sh('make all -j' + str(num_processors), cwd=build_path) #log_file
    else:
        # No makefile -- nothing to build, only package. We expect that
        # debian/rules will have enough information
        pass

def clean(proj_name, proj_dir):
    out('Cleaning project \'' + proj_name + '\'')

    #compute required paths
    code_path = get_code_path(proj_name, proj_dir)
    build_path = get_build_path(proj_name)
    build_pkg_path = get_build_pkg_path(proj_name)

    if os.path.isdir(build_path):
        shutil.rmtree(build_path)

    if os.path.isdir(build_pkg_path):
        files=os.listdir(build_pkg_path)
        for f in files:
            if (re.search('\.deb$', f) or
                re.search('\.changes$', f) or
                re.search('\.build$', f) or
                re.search('\.dsc$', f)):
                os.remove(os.path.join(build_pkg_path, f))

def reconf(proj_name, proj_dir):
    out('Reconfiguring project \'' + proj_name + '\'')

    #compute required paths
    code_path = get_code_path(proj_name, proj_dir)

    if os.path.exists(code_path + '/configure.ac'):
        sh('autoreconf', cwd=code_path) #log_file
    elif os.path.exists(code_path + '/CMakeLists.txt'):
        sh('cmake .', cwd=code_path) #log_file


def check_build(proj_name, proj_dir,do_check=True):
    if not do_check:
        return

    out('Checking project \'' + proj_name + '\'')

    #compute required paths
    log_file = get_log_path(proj_name)
    build_path = get_build_path(proj_name)

    # launch make check
    sh('make check -j' + str(num_processors), cwd=build_path) #log_file
    #sh('make distcheck', cwd=build_path) #log_file

#first arg carries the project name
#second arg: if 'do_source', a source package is build. Other values are ignored
def package(proj_name, proj_dir, do_source=False):
    out('Packaging project \'' + proj_name + '\'')

    #compute required paths
    log_file = get_log_path(proj_name)
    code_path = get_code_path(proj_name, proj_dir)
    build_path = get_build_path(proj_name)
    build_pkg_path = get_build_pkg_path(proj_name)
    pkg_path = get_pkg_path(proj_name)

    #make distributable
    sh('make dist', cwd=build_path) #log_file

    # find the resulting distributable tar file. Loosely match with the projects
    # name, take the the tgz which matches the largest number of words in the
    # projects name
    tgzs = os.listdir(build_path)
    tgzs = [ tgz for tgz in tgzs if tgz.endswith('.tar.gz') ]

    dist_file = None
    if len(tgzs) == 0:
        pass
    elif len(tgzs) == 1:
        dist_file = tgzs[0]
    else:
        words = re.split(r'[-_ ]', proj_name)
        max_tgz = ''
        max_score = 0
        for tgz in tgzs:
            score = 0
            for word in words:
                if tgz.find(word) != -1:
                    score += len(word)
            if score > max_score:
                max_tgz = tgz
                max_score = score

        if max_score > 0:
            dist_file = max_tgz

    if dist_file == None:
        out("ERROR: Could not find distributable package")
        sys.exit(1)

    m = re.match('^(.*)-([^-]*)\.tar\.gz$', dist_file, re.I)
    if not m:
        out('ERROR: could not parse the filename of an archive ' + dist_file)
        sys.exit(1)

    base = m.group(1)
    version = m.group(2)

    tar_file = build_pkg_path + '/' + base + '_' + version + '.orig.tar.gz'
    tar_path = build_pkg_path + '/' + base + '-' + version

    #make the debian dir
    if not os.path.isdir(build_pkg_path):
        os.makedirs(build_pkg_path)

    #move the distributable to the destination directory and cleanly extract it
    shutil.move(build_path + '/' + dist_file, tar_file)
    if os.path.isdir(tar_path):
        shutil.rmtree(tar_path)

    sh('tar -xzf ' + tar_file + ' -C ' + build_pkg_path, cwd=build_pkg_path)

    #check if successful
    if not os.path.isdir(tar_path):
        out("ERROR: Failed to extract distributable archive to " + tar_path)
        sys.exit(1)

    #check for debian config folder, create one using dh_make if not existing
    if not os.path.isdir(tar_path + '/debian'):
        #debian config folder is not distributed
        if os.path.isdir(pkg_path + '/debian'):
            #found one in packaging dir
            shutil.copytree(pkg_path + '/debian', tar_path + '/debian')
        elif os.path.isdir(code_path + '/debian'):
            #found one in code dir
            shutil.copytree(code_path + '/debian', tar_path + '/debian')
        else:
            #no debian config folder exists -> create one and fail
            sh('dh_make -f ' + tar_file, cwd=tar_path) #log_file
            shutil.copytree(tar_path + '/debian', build_pkg_path + '/debian')

            out("ERROR: Please update the debian configs at $build_pkg_path/debian")
            sys.exit(1)

    #clear the directory
    sh('find . -iname "*.deb" -exec rm -f \'{}\' \;', cwd=build_pkg_path) #log_file

    #make debian package
    global root_path

    if (do_source == True):
        r = sh('debuild --no-lintian -S -sa -k0x0374452d ',
                 cwd=tar_path) #log_file
        if r != 0:
            out("ERROR: Building project "+ proj_name + " failed")
            sys.exit(1)
    else:
        r = sh('debuild --no-lintian --build-hook="' + copy_build_files_path + ' ' + build_path+'" -sa -k0x0374452d ',
                cwd=tar_path) #log_file
        if r != 0:
            out("ERROR: Building project "+ proj_name + " failed")
            sys.exit(1)


def install(proj_name, proj_dir):
    #compute required paths
    build_pkg_path = get_build_pkg_path(proj_name)

    #install the package(s)
    sh('pkg=$(echo *.deb); gksu "dpkg -i $pkg"', cwd=build_pkg_path) #log_file

def debinstall(proj_name, proj_dir):
    #compute required paths
    build_pkg_path = get_build_pkg_path(proj_name)
    global archive_path

    #compute required paths
    log_file = get_log_path(proj_name)
    code_path = get_code_path(proj_name, proj_dir)
    build_path = get_build_path(proj_name)
    build_pkg_path = get_build_pkg_path(proj_name)

    #install the package(s)
    debs = os.listdir(build_pkg_path)
    for deb in debs:
        if deb.endswith('.deb'):
            shutil.copyfile(build_pkg_path + '/' + deb, archive_path + '/' + deb)
    sh('./reload', cwd=archive_path) #log_file

#shows the available options to the stderr
def show_help():
    sys.stderr.write("""
Usage:

make_all.sh [action] [projects ...]

Actions:

 --build -b - builds the source tree

 --clean -n - cleans the build tree

 --package -p - builds the source tree and creates a binary package

 --package_source -s - builds the source tree and creates a source
   package

 --install -i - builds the source tree, creates a binary package and
   installs it both to the system and to a local repository

 --reinstall -I - reintalls already built binary packages both to the
   system and to a local repository

 --debinstall -d - builds the source tree, creates a binary package
   and installs it only to a local repository

 --debreinstall -D - reintalls already built binary packages to a
   local repository

 --nocheck -n - does not check the package after building

 --help  - displays this text
 """)
    #indentation

for path in build_path, build_pkg_path, pkg_path:
    if not os.path.exists(path):
        os.makedirs(path)

projects_to_build=[]

# get the list of available projects
available_projects = []
for proj_dir in project_dirs:
    try:
        projects = os.listdir(proj_dir)
    except:
        continue

    for proj_name in projects:
        curr_proj_dir = os.path.join(proj_dir, proj_name)
        if os.path.isdir(curr_proj_dir):
            available_projects.append((curr_proj_dir, proj_name))

# parse arguments
if (len(sys.argv) <= 1):
    out("ERROR: no name of project provided")
    out("Available projects: ")

    for d,p in available_projects:
        out( '\"' + p + '\"' + ' in directory ' + d)
    sys.exit(1)

action=None
do_check = True

sys.argv.pop(0)
for arg in sys.argv:
    if (arg=='-c' or arg=='--clean'):
        action='clean'
    elif (arg=='-f' or arg=='--full_clean'):
        action='full_clean'
    elif (arg=='-b' or arg=='--build'):
        action="build"
    elif (arg=='-p' or arg=='--package'):
        action="package"
    elif (arg=='-s' or arg=='--package_source'):
        action="package_source"
    elif (arg=='-i' or arg=='--install'):
        action="install"
    elif (arg=='-I' or arg=='--reinstall'):
        action="reinstall"
    elif (arg=='-d' or arg=='--debinstall'):
        action="debinstall"
    elif (arg=='-D' or arg=='--debreinstall'):
        action="debreinstall"
    elif (arg=='-n' or arg=='--nocheck'):
        do_check = False
    elif (arg=='--help'):
        show_help()
        sys.exit(1)
    else:
        if not arg.startswith('-'):
            projects_to_build.append(arg)

# check received arguments
checked_projects = []

for proj in projects_to_build:
    for (d,p) in available_projects:
        if p.find(proj) != -1:
            checked_projects.append((d, p))

if len(checked_projects) > 0:
    out("Found projects: ")
    for d,p in checked_projects:
        out('\"' + p + '\"' + ' in directory ' + d)
else:
    out("ERROR: Project not found. Abort. ")
    sys.exit(1)

if (action == None):
    out("WARN: Action not specified. Defaulting to compile+package+install")
    action = "install"

# do work
if (action == 'full_clean'):
    for (d,p) in checked_projects:
        reconf(p,d)
        clean(p,d)

elif (action == 'clean'):
    for (d,p) in checked_projects:
        clean(p,d)

elif (action == 'build'):
    for (d,p) in checked_projects:
        build(p,d)
        check_build(p,d,do_check)

elif (action == 'package'):
    for (d,p) in checked_projects:
        build(p,d)
        check_build(p,d,do_check)
        package(p,d)

elif (action == 'package_source'):
    for (d,p) in checked_projects:
        build(p,d)
        check_build(p,d,do_check)
        package(p,d,do_source=True)

elif (action == 'install'):
    for (d,p) in checked_projects:
        build(p,d)
        check_build(p,d,do_check)
        package(p,d)

        out("Installing project: " + p)
        install(p,d)
        debinstall(p,d)

elif (action == 'reinstall'):
    for (d,p) in checked_projects:
        out("Installing project: " + p)
        install(p,d)
        debinstall(p,d)

elif (action == 'debinstall'):
    for (d,p) in checked_projects:
        build(p,d)
        check_build(p,d,do_check)
        package(p,d)

        out("Installing project: " + p)
        debinstall(p,d)

elif (action == 'debreinstall'):
    for (d,p) in checked_projects:
        out("Installing project: " + p)
        debinstall(p,d)

else:
    out("ERROR: Wrong action!" + action)
    sys.exit(1)

out("Success!")

