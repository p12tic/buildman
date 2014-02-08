#!/usr/bin/env python3

#    Copyright (C) 2011-2014  Povilas Kanapickas <povilas@radix.lt>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>

import os
import os.path
import glob
from subprocess import call
import shutil
import re
import glob
import sys

#directory layout configuration
root_path = os.environ['HOME'] + '/code/my/'
archive_path = os.environ['HOME'] + '/downloads/apt/'

copy_build_files_path = root_path + '/../my/copy_build_files.py'

num_processors = 2

build_path =     root_path + "build/"
build_pkg_path = root_path + "build_packaging/"
build_deb_pkg_path = root_path + "build_debian/"
pkg_path =       root_path + "checkouts_packaging/"
log_path =       root_path + "log/"

log_ext = "build_log"

# the ID of the key that debian sources and binaries should be signed with
# or None if signing is not wanted
debian_sign_key = '0x0374452d'

project_dirs = [
    root_path + 'checkouts/',
    root_path + 'local/',
    root_path + 'mods/'
    ]

deb_project_dirs = [
    root_path + 'checkouts_debian/'
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

BUILD_TYPE_NONE=0
BUILD_TYPE_AUTOTOOLS=1
BUILD_TYPE_CMAKE=2
BUILD_TYPE_QMAKE=3
BUILD_TYPE_MAKEFILE=4

VCS_TYPE_NONE=0
VCS_TYPE_GIT=1

def add_configure_args(proj_name):
    if re.search(r'wnckmm', proj_name):
        return '--enable-maintainer-mode'
    return '--prefix=/usr'

class Project:

    def __init__(self, proj_name, proj_dir):
        self.proj_name = proj_name
        self.proj_dir = proj_dir

        global log_path, build_path, pkg_path, build_pkg_path

        self.log_file = os.path.join(log_path, self.proj_name)
        self.code_path = self.proj_dir
        self.build_path = os.path.join(build_path, self.proj_name)
        self.pkg_path = os.path.join(pkg_path, self.proj_name)
        self.build_pkg_path = os.path.join(build_pkg_path, self.proj_name)
        self.build_pkgver_path = None

        self.build_type = self.get_build_type()
        self.vcs_type = self.get_vcs_type()

    def get_build_type(self):

        if (os.path.exists(self.code_path + '/configure') or
            os.path.exists(self.code_path + '/configure.ac')):
            return BUILD_TYPE_AUTOTOOLS
        if glob.glob(self.code_path + "/*.pro"):
            return BUILD_TYPE_QMAKE
        if os.path.exists(self.code_path + '/CMakeLists.txt'):
            return BUILD_TYPE_CMAKE
        if os.path.exists(self.code_path + "/Makefile"):
            return BUILD_TYPE_MAKEFILE
        return BUILD_TYPE_NONE

    def get_vcs_type(self):

        if os.path.isdir(self.code_path + '/.git'):
            return VCS_TYPE_GIT
        return VCS_TYPE_NONE

    def build(self):
        out('Configuring project \'' + self.proj_name + '\'')

        out("Code path: " + self.code_path)
        out("Build path: " + self.build_path)
        out("Pkg build path: " + self.build_pkg_path)
        out("Pkg path: " + self.pkg_path)

        if self.build_type == BUILD_TYPE_AUTOTOOLS:
            #autotools project

            #get modification time of the build directory, create if it does not exist

            if os.path.isdir(self.build_path):
                build_mtime = os.path.getmtime(self.build_path)
            else:
                os.makedirs(self.build_path)
                build_mtime = 0.0

            ac_mtime = os.path.getmtime(self.code_path + '/configure.ac')
            if os.path.isfile(self.code_path + '/configure'):
                c_mtime = os.path.getmtime(self.code_path + '/configure')
            else:
                c_mtime = 0.0

            #rerun autoconf if needed
            if c_mtime < ac_mtime:
                sh('autoconf; automake', cwd=self.code_path)
                c_mtime = os.path.getmtime(self.code_path + '/configure')

            #reconfigure if needed

            if build_mtime < c_mtime:
                shutil.rmtree(self.build_path)
                os.makedirs(self.build_path)
                sh(self.code_path + '/configure ' + add_configure_args(self.proj_name),
                   cwd=self.build_path)

            #build
            out('Building project \'' + self.proj_name + '\'')
            sh('make all -j' + str(num_processors), cwd=self.build_path)

        elif self.build_type == BUILD_TYPE_CMAKE:
            # cmake project

            if not os.path.isdir(self.build_path):
                os.makedirs(self.build_path)

            cmd = 'cmake \'' + self.code_path + '\''
            out(cmd)
            sh('cmake \"' + self.code_path + '\"' , cwd=self.build_path)

            out('Building project \'' + self.proj_name + '\'')
            sh('make all -j' + str(num_processors), cwd=self.build_path)

        elif self.build_type == BUILD_TYPE_QMAKE:
            # qmake project
            if not os.path.isdir(build_path):
                os.makedirs(build_path)

            cmd = 'qmake \'' + self.code_path + '\''
            out(cmd)

            # work around the issues with qmake out-of-source builds
            # In short, only directories at the same level are supported
            code_dir = '.' + self.proj_name + '_codedir'
            sh('ln -fs \"' + self.code_path + '\" \"../' + code_dir + '\" ', cwd=build_path)

            sh('qmake \"../' + code_dir + '\"' , cwd=build_path)

            out('Building project \'' + self.proj_name + '\'')
            sh('make all -j' + str(num_processors), cwd=build_path)

        elif self.build_type == BUILD_TYPE_MAKEFILE:
            #simple makefile project. Rebuild everything on any update in the source tree

            #get modification time of the build directory, create if it does not exist
            if os.path.isdir(self.build_path):
                build_mtime = get_dir_mtime(self.build_path)
            else:
                os.makedirs(self.build_path)
                build_mtime = 0

            c_mtime = get_dir_mtime(self.code_path)

            if (build_mtime < c_mtime):
                out('Building project \'' + self.proj_name + '\'')

                shutil.rmtree(self.build_path)
                shutil.copytree(self.code_path, self.build_path)

                sh('make all -j' + str(num_processors), cwd=self.build_path)
        else:
            # No makefile -- nothing to build, only package. We expect that
            # debian/rules will have enough information
            out('... (no Makefile)')

    def clean(self):
        out('Cleaning project \'' + self.proj_name + '\'')

        if os.path.isdir(self.build_path):
            shutil.rmtree(self.build_path)

        if os.path.isdir(self.build_pkg_path):
            files=os.listdir(self.build_pkg_path)
            for f in files:
                if (re.search('\.deb$', f) or
                    re.search('\.changes$', f) or
                    re.search('\.build$', f) or
                    re.search('\.dsc$', f)):
                    os.remove(os.path.join(self.build_pkg_path, f))

    def reconf(self):
        out('Reconfiguring project \'' + self.proj_name + '\'')

        if self.build_type == BUILD_TYPE_AUTOTOOLS:
            sh('autoreconf', cwd=self.code_path)
        elif self.build_type == BUILD_TYPE_CMAKE:
            sh('cmake .', cwd=self.code_path)

    def check_build(self, do_check=True):
        if not do_check:
            return

        out('Checking project \'' + self.proj_name + '\'')

        if self.build_type != BUILD_TYPE_NONE:
            # launch make check
            mkpath = os.path.join(self.build_path, 'Makefile')
            if os.path.exists(mkpath):
                mk = open(mkpath).read()
                if re.search(r'\bcheck:', mk):
                    sh('make check -j' + str(num_processors), cwd=self.build_path)
                else:
                    out('... (no check rule)')
            else:
                out('... (no Makefile)')

            #sh('make distcheck', cwd=self.build_path)
        else:
            out('... (no Makefile)')

    def find_debian_folder(self):
        if os.path.isdir(self.pkg_path + '/debian'):
            return self.pkg_path + '/debian'
        if os.path.isdir(self.code_path + '/debian'):
            return self.code_path + '/debian'
        out('ERROR: debian folder could not be found')
        sys.exit(1)

    def extract_changelog_version(self, deb_folder):
        ch_fn = deb_folder + '/changelog'
        if not os.path.exists(ch_fn):
            out('ERROR: could not extract debian changelog')
            sys.exit(1)
        for line in open(ch_fn).readlines():
            if line:
                m = re.match(r'^\s*([\w_+-.]+)\s*\(([\w_.:+~]+)-([\w_.:]+)', line)
                if not m:
                    out('ERROR: could not match changelog line: \"' + line + '\"')
                    sys.exit(1)
                name = m.group(1)
                ver = m.group(2)
                deb_ver = m.group(3)

                # strip epoch
                if ':' in ver:
                    epoch,sep,ver = ver.rpartition(':')

                return (name, ver, deb_ver)
        out('ERROR: could not match any changelog line')
        sys.exit(1)

    # imports debian directory for a project extracted to ext_tar_path. Exits
    # on failure
    def import_debian_dir(self, tar_file, ext_tar_path):
        if not os.path.isdir(ext_tar_path + '/debian'):
            #debian config folder is not distributed
            if os.path.isdir(self.pkg_path + '/debian'):
                #found one in packaging dir
                out("Debian dir in packaging repo: " + self.pkg_path + '/debian')
                shutil.copytree(self.pkg_path + '/debian', ext_tar_path + '/debian')
            elif os.path.isdir(self.code_path + '/debian'):
                #found one in code dir
                out("Debian dir in code repo: " + self.code_path + '/debian')
                shutil.copytree(self.code_path + '/debian', ext_tar_path + '/debian')
            else:
                #no debian config folder exists -> create one and fail
                sh('dh_make -f ' + tar_file, cwd=ext_tar_path)
                shutil.copytree(ext_tar_path + '/debian', self.build_pkg_path + '/debian')

                out("ERROR: Please update the debian configs at $build_pkg_path/debian")
                sys.exit(1)
        else:
            out("WARN: Debian dir is distributed with the source package")

    # Finds the distributable tar.gz archive created by the make dist rule.
    # All tar.gz files within the build path are loosely matched with the
    # project name. The file which matches the largest number of words in the
    # projects name is selected.
    #
    # Returns None on failure
    def find_dist_tgz(self):
        tgzs = os.listdir(self.build_path)
        tgzs = [ tgz for tgz in tgzs if tgz.endswith('.tar.gz') ]

        dist_file = None
        if len(tgzs) == 0:
            pass
        elif len(tgzs) == 1:
            dist_file = tgzs[0]
        else:
            words = re.split(r'[-_ ]', self.proj_name)
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
        return dist_file

    ''' Creates a distributable by using make dist for autotools or makefile
        projects or exporting the current git work tree
        Returns a tuple containing the following data:
            base - the name of the project
            version - the version of the project
            dist_file - the distributable tarball
    '''
    def make_distributable_make_dist(self):
        out('Using make dist packager')
        sh('make dist', cwd=self.build_path)

        dist_file = self.find_dist_tgz()

        if dist_file == None:
            out("ERROR: Could not find distributable package")
            sys.exit(1)

        m = re.match('^(.*)-([^-]*)\.tar\.gz$', dist_file, re.I)
        if not m:
            out('ERROR: could not parse the filename of an archive ' + dist_file)
            sys.exit(1)

        base = m.group(1)
        version = m.group(2)
        dist_file = os.path.join(self.build_path, dist_file)
        return (base, version, dist_file)

    def make_distributable_git_archive(self):
        out('Using git packager')

        base,version,deb_version = self.extract_changelog_version(self.find_debian_folder())
        tar_base = base + '-' + version
        dist_file = tar_base + '.tar.gz'
        sh('git archive --worktree-attributes --prefix=\"' + tar_base
            + '/' + '\" HEAD --format=tar.gz > \"' + dist_file + '\"',
            cwd=self.code_path)

        dist_file = os.path.join(self.code_path, dist_file)
        return (base, version, dist_file)

    # Checks the project makefile for dist target
    def does_makefile_contain_dist_target(self):
        f = open(self.code_path + "/Makefile")
        for l in f:
            if l.startswith("dist:"):
                return True
        return False

    def make_distributable(self):

        #make a distributable archive
        if self.build_type == BUILD_TYPE_AUTOTOOLS:
            return self.make_distributable_make_dist()

        elif (self.build_type == BUILD_TYPE_MAKEFILE and
              self.does_makefile_contain_dist_target()):
            return self.make_distributable_make_dist()

        elif self.vcs_type == VCS_TYPE_GIT:
            return self.make_distributable_git_archive()

        else:
            out('ERROR: VCS and project type not supported')
            sys.exit(1)

    def package(self, do_source=False):
        out('Packaging project \'' + self.proj_name + '\'')

        (base,version,dist_file) = self.make_distributable()
        tar_base = base + '-' + version

        out('File: ' + dist_file)
        out('Name: ' + base + '; version: ' + version)

        self.build_pkgver_path = self.build_pkg_path + '/' + version
        tar_file = self.build_pkgver_path + '/' + base + '_' + version + '.orig.tar.gz'
        tar_path = self.build_pkgver_path + '/' + tar_base

        # create a clean build dir
        if os.path.isdir(self.build_pkgver_path):
            shutil.rmtree(self.build_pkgver_path)
        os.makedirs(self.build_pkgver_path)

        #move the distributable to the destination directory and cleanly extract it
        shutil.move(dist_file, tar_file)
        sh('tar -xzf ' + tar_file + ' -C ' + self.build_pkgver_path, cwd=self.build_pkgver_path)

        #check if successful
        if not os.path.isdir(tar_path):
            out("ERROR: Failed to extract distributable archive to " + tar_path)
            sys.exit(1)

        # import debian config folder
        self.import_debian_dir(tar_file, tar_path)

        #make debian package
        self.debuild(tar_path, do_source)

    # Returns arguments for dpkg package signing utility
    def get_key_arg(self):
        if (debian_sign_key == None):
            return ' -us -uc'
        else:
            return ' -k' + debian_sign_key

    # Runs debuild in the tar_path directory
    def debuild(self, tar_path, do_source):
        global root_path
        global debian_sign_key

        key_arg = self.get_key_arg()

        if (do_source == True):
            r = sh('debuild --no-lintian -S -sa ' + key_arg,
                    cwd=tar_path)
            if r != 0:
                out("ERROR: Building project "+ self.proj_name + " failed")
                sys.exit(1)
        else:
            r = sh('debuild --no-lintian --build-hook="' + copy_build_files_path + ' ' + self.build_path+'" -sa ' + key_arg,
                    cwd=tar_path)
            if r != 0:
                out("ERROR: Building project "+ self.proj_name + " failed")
                sys.exit(1)

    def package_pristine(self, do_source=False):
        deb_dir = os.path.join(self.code_path, 'debian')

        # check is deb_dir exists
        if not os.path.isdir(deb_dir):
            out("ERROR: No debian directory for project " + self.proj_name)
            sys.exit(1)

        (name, version, deb_version) = self.extract_changelog_version(deb_dir)

        self.build_pkgver_path = self.build_pkg_path + '/' + version
        if do_source:
            self.build_pkgver_path += '_source'

        # create a clean build dir
        if os.path.isdir(self.build_pkgver_path):
            shutil.rmtree(self.build_pkgver_path)
        os.makedirs(self.build_pkgver_path)

        key_arg = self.get_key_arg()

        if do_source:
            sh('git-buildpackage --git-pristine-tar --git-export-dir="' +
               self.build_pkgver_path + '" -S -sa ' + key_arg, cwd=self.code_path)
        else:
            sh('git-buildpackage --git-pristine-tar --git-export-dir="' +
               self.build_pkgver_path + '" -sa ' + key_arg, cwd=self.code_path)


    def get_latest_pkgver(self):
        versions = []
        for d in os.listdir(self.build_pkg_path):
            d = os.path.join(self.build_pkg_path, d)
            if os.path.isdir(d):
                versions.append(d)

        return max(versions, key=os.path.getmtime)

    def install(self):
        #install the package(s)
        if self.build_pkgver_path == None:
            self.build_pkgver_path = self.get_latest_pkgver()

        sh('pkg=$(echo *.deb); gksu "dpkg -i $pkg"', cwd=self.build_pkgver_path)

    def debinstall(self):
        global archive_path

        if self.build_pkgver_path == None:
            self.build_pkgver_path = self.get_latest_pkgver()

        #install the package(s)
        debs = os.listdir(self.build_pkgver_path)
        for deb in debs:
            if deb.endswith('.deb'):
                shutil.copyfile(self.build_pkgver_path + '/' + deb, archive_path + '/' + deb)
        sh('./reload', cwd=archive_path)

#shows the available options to the stderr
def show_help():
    sys.stderr.write("""
Usage:

make_all.sh [options] [projects ...]

Options:

 --build -b - builds the source tree

 --clean -n - cleans the build tree

 --full_clean -f - cleans the build tree and reconfigures the source
   tree (if possible)

 --package -p - builds the source tree and creates a binary package

 --package_source -s - builds the source tree and creates a source
   package

 --install -i - builds the source tree, creates a binary package and
   installs it both to the system and to a local repository

 --reinstall -I - reintalls most recently built binary packages both
   to the system and to a local repository.

 --debinstall -d - builds the source tree, creates a binary package
   and installs it only to a local repository

 --debreinstall -D - reintalls most recently built binary packages to
   a local repository

 --pristine - Package or install a pristine project. Must not be used
   along the --build, --clean or --full_clean flags.

 --nocheck -n - does not check the package after building

 --help  - displays this text
 """)
    #indentation

projects_to_build=[]

def get_available_projects(dirs):
    # get the list of available projects
    available_projects = []
    for d in dirs:
        try:
            projects = os.listdir(d)
        except:
            continue

        for name in projects:
            pdir = os.path.join(d, name)
            if os.path.isdir(pdir):
                available_projects.append((pdir, name))
    return available_projects

# parse arguments
if (len(sys.argv) <= 1):
    out("ERROR: no name of project provided")
    out("Available projects: ")

    for d,p in get_available_projects(dirs):
        out( '\"' + p + '\"' + ' in directory ' + d)
    sys.exit(1)

action=None
do_check = True
pristine = False

ACTION_CLEAN=1
ACTION_FULL_CLEAN=2
ACTION_BUILD=3
ACTION_PACKAGE=4
ACTION_PACKAGE_SOURCE=5
ACTION_INSTALL=6
ACTION_REINSTALL=7
ACTION_DEBINSTALL=8
ACTION_DEBREINSTALL=9

sys.argv.pop(0)
for arg in sys.argv:
    if (arg=='-c' or arg=='--clean'):
        action = ACTION_CLEAN
    elif (arg=='-f' or arg=='--full_clean'):
        action = ACTION_FULL_CLEAN
    elif (arg=='-b' or arg=='--build'):
        action = ACTION_BUILD
    elif (arg=='-p' or arg=='--package'):
        action = ACTION_PACKAGE
    elif (arg=='-s' or arg=='--package_source'):
        action = ACTION_PACKAGE_SOURCE
    elif (arg=='-i' or arg=='--install'):
        action = ACTION_INSTALL
    elif (arg=='-I' or arg=='--reinstall'):
        action = ACTION_REINSTALL
    elif (arg=='-d' or arg=='--debinstall'):
        action = ACTION_DEBINSTALL
    elif (arg=='-D' or arg=='--debreinstall'):
        action = ACTION_DEBREINSTALL
    elif (arg=='-n' or arg=='--nocheck'):
        do_check = False
    elif arg=='--pristine':
        pristine = True
    elif (arg=='--help'):
        show_help()
        sys.exit(1)
    else:
        if not arg.startswith('-'):
            projects_to_build.append(arg)

if pristine:
    if action in [ ACTION_CLEAN, ACTION_FULL_CLEAN, ACTION_BUILD]:
        out("ERROR: --pristine must not be used along with --clean, "
            "--full_clean and --build")
        sys.exit(1)
    project_dirs = deb_project_dirs
    build_pkg_path = build_deb_pkg_path

# check received projects
checked_projects = []

ident=None
available_projects = get_available_projects(project_dirs)
for proj in projects_to_build:
    for (d,p) in available_projects:
        if p == proj:
            ident=(d, p)
            break
        if p.find(proj) != -1:
            checked_projects.append((d, p))

for path in build_path, build_pkg_path:
    if not os.path.exists(path):
        os.makedirs(path)

# if identical, ignore other
if ident != None:
    checked_projects = [(d, p)]

if len(checked_projects) > 0:
    out("Found projects: ")
    for d,p in checked_projects:
        out('\"' + p + '\"' + ' in directory ' + d)
else:
    out("ERROR: Project not found. Abort. ")
    sys.exit(1)

if (action == None):
    out("WARN: Action not specified. Defaulting to compile+package+install")
    action = ACTION_INSTALL

# do work
if (action == ACTION_FULL_CLEAN):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        pr.reconf()
        pr.clean()

elif (action == ACTION_CLEAN):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        pr.clean()

elif (action == ACTION_BUILD):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        pr.build()
        pr.check_build(do_check)

elif (action == ACTION_PACKAGE):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        if pristine:
            pr.package_pristine()
        else:
            pr.build()
            pr.check_build(do_check)
            pr.package()

elif (action == ACTION_PACKAGE_SOURCE):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        if pristine:
            pr.package_pristine(do_source=True)
        else:
            pr.build()
            pr.check_build(do_check)
            pr.package(do_source=True)

elif (action == ACTION_INSTALL):
    for (d,p) in checked_projects:
        pr = Project(p,d)

        if pristine:
            pr.package_pristine()
        else:
            pr.build()
            pr.check_build(do_check)
            pr.package()

        out("Installing project: " + p)
        pr.install()
        pr.debinstall()

elif (action == ACTION_REINSTALL):
    for (d,p) in checked_projects:
        pr = Project(p,d)
        out("Installing project: " + p)
        pr.install()
        pr.debinstall()

elif (action == ACTION_DEBINSTALL):
    for (d,p) in checked_projects:
        pr = Project(p,d)

        if pristine:
            pr.package_pristine()
        else:
            pr.build()
            pr.check_build(do_check)
            pr.package()

        out("Installing project: " + p)
        pr.debinstall()

elif (action == ACTION_DEBREINSTALL):
    for (d,p) in checked_projects:
        out("Installing project: " + p)
        pr = Project(p,d)
        pr.debinstall()

else:
    out("ERROR: Wrong action!" + action)
    sys.exit(1)

out("Success!")

