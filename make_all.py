#!/usr/bin/env python3

#    Copyright (C) 2011-2020  Povilas Kanapickas <povilas@radix.lt>
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

import argparse
import enum
import json
import os
import glob
import subprocess
import shutil
import re
import sys


_cached_config = None


def get_config():
    ''' Supported keys:

        num_cores (int): The number of cores to use when building

        debian_sign_key (str): The ID of the key to use for signing the packages.
            If missing or None, the packages won't be signed.
    '''
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    config_path = os.path.join(os.environ['HOME'], '.config', 'p12build.json')
    if not os.path.exists(config_path):
        raise Exception('Config path does not exist')
    with open(config_path) as config_f:
        _cached_config = json.load(config_f)
        return _cached_config


def get_config_key(project, key, default):
    config = get_config()
    if 'projects' in config and project in config['projects']:
        config_project = config['projects'][project]
        if key in config_project:
            return config_project[key]

    return config.get(key, default)


def get_config_cpu_cores(project):
    return get_config_key(project, 'num_cores', 1)


def get_config_debian_sign_key(project):
    return get_config_key(project, 'debian_sign_key', None)


def get_config_dist_method(project):
    return get_config_key(project, 'dist_method', None)


def get_config_embedded_packaging_dir(project):
    return get_config_key(project, 'embedded_packaging_dir', None)


# directory layout configuration
class PathConf:

    def __init__(self):
        self.set_pbuilder_dist('unstable')

    def set_pbuilder_dist(self, dist):
        if '-' in dist:
            dist_suite = dist
            dist = dist.split('-')[0]
            self.pbuilder_suite = dist_suite
        else:
            self.pbuilder_suite = dist

        self.pbuilder_distribution = dist
        self.init_paths()

    def init_paths(self):
        self.home_path = os.environ['HOME']
        self.root_path = os.path.join(self.home_path, 'code/my')
        self.archive_path = os.path.join(self.home_path, 'code/apt')

        self.build_path = os.path.join(self.root_path, "build")
        self.build_pkg_path = os.path.join(self.root_path, "build_packaging")
        self.build_deb_pkg_path = os.path.join(self.root_path, "build_debian")
        self.build_pbuilder_path = os.path.join(self.root_path,
                                                'build_pbuilder')
        self.pkg_path = os.path.join(self.root_path, "checkouts_packaging")
        self.log_path = os.path.join(self.root_path, "log")

        project_fns = ['checkouts', 'local', 'mods']

        self.project_dirs = [os.path.join(self.root_path, fn)
                             for fn in project_fns]

        deb_project_fns = ['checkouts_debian', 'mods_debian']

        self.deb_project_dirs = [os.path.join(self.root_path, fn)
                                 for fn in deb_project_fns]

        # Pbuilder-specific options
        self.pbuilder_mirror = 'http://ftp.lt.debian.org/debian/'

        self.pbuilder_othermirror = None
        if self.pbuilder_suite != self.pbuilder_distribution:
            self.pbuilder_othermirror = \
                'deb {0} {1} main'.format(self.pbuilder_mirror,
                                          self.pbuilder_suite)

        self.pbuilder_workdir_path = \
            os.path.join(self.build_pbuilder_path, "workdir")
        self.pbuilder_cache_path = \
            os.path.join(self.build_pbuilder_path, "aptcache")
        self.pbuilder_tgz_path = \
            os.path.join(self.build_pbuilder_path, "base_tgzs")

        self.pbuilder_tgz = \
            os.path.join(self.pbuilder_tgz_path,
                         'base_' + self.pbuilder_suite + '.tgz')


def out(s):
    if isinstance(s, list):
        s = str(s)
    sys.stdout.write(s + '\n')
    sys.stdout.flush()


def sh(cmd, cwd, env=None):
    out('DBG: Executing {0}'.format(cmd))
    if isinstance(cmd, list):
        code = subprocess.call(cmd, cwd=cwd, env=env)
    else:
        code = subprocess.call(cmd, shell=True, cwd=cwd, env=env)
    if code != 0:
        out('ERROR: Command \'{0}\' returned code {1}'.format(cmd, code))
        sys.exit(code)
    return code


def get_dir_mtime(path):
    max_mtime = 0
    for dirname, subdirs, files in os.walk(path):
        if re.search(r'\.git', dirname):
            continue
        for fname in files:
            mtime = os.path.getmtime(os.path.join(dirname, fname))
            if mtime > max_mtime:
                max_mtime = mtime
    return max_mtime


class BuildType(enum.Enum):
    NONE = 0
    AUTOTOOLS = 1
    CMAKE = 2
    QMAKE = 3
    MAKEFILE = 4


class VcsType(enum.Enum):
    NONE = 0
    GIT = 1


def get_configure_args(proj_name):
    config_path = os.path.join(os.environ['HOME'], '.config', 'p12build', 'configure-' + proj_name)
    if not os.path.exists(config_path):
        return ['--prefix=/usr/local']

    with open(config_path) as f:
        return f.readlines()


def get_pbuilder_othermirror_opt(othermirror):
    if othermirror is None:
        return []
    return ['--othermirror', othermirror]


class Project:

    def __init__(self, paths, proj_name, proj_dir):
        self.paths = paths
        self.proj_name = proj_name
        self.proj_dir = proj_dir

        self.log_file = os.path.join(self.paths.log_path, self.proj_name)
        self.code_path = self.proj_dir
        self.build_path = os.path.join(self.paths.build_path, self.proj_name)
        self.pkg_path = os.path.join(self.paths.pkg_path, self.proj_name)
        self.build_pkg_path = os.path.join(self.paths.build_pkg_path,
                                           self.proj_name)
        self.build_pkgver_path = None

        self.build_type = self.get_build_type()
        self.vcs_type = self.get_vcs_type()

    def get_build_type(self):

        if (os.path.exists(self.code_path + '/configure') or
                os.path.exists(self.code_path + '/configure.ac')):
            return BuildType.AUTOTOOLS
        if glob.glob(self.code_path + "/*.pro"):
            return BuildType.QMAKE
        if os.path.exists(self.code_path + '/CMakeLists.txt'):
            return BuildType.CMAKE
        if os.path.exists(self.code_path + "/Makefile"):
            return BuildType.MAKEFILE
        return BuildType.NONE

    def get_vcs_type(self):

        if os.path.isdir(self.code_path + '/.git'):
            return VcsType.GIT
        return VcsType.NONE

    def build(self, do_build=True):
        if not do_build:
            return

        out('Configuring project \'{0}\''.format(self.proj_name))

        out("Code path: \'{0}\'".format(self.code_path))
        out("Build path: \'{0}\'".format(self.build_path))
        out("Pkg build path: \'{0}\'".format(self.build_pkg_path))
        out("Pkg path: \'{0}\'".format(self.pkg_path))

        if self.build_type == BuildType.AUTOTOOLS:
            # autotools project

            # get modification time of the build directory,
            # create if it does not exist

            if os.path.isdir(self.build_path):
                build_mtime = os.path.getmtime(self.build_path)
            else:
                os.makedirs(self.build_path)
                build_mtime = 0.0

            configure_path = os.path.join(self.code_path, 'configure')
            ac_mtime = os.path.getmtime(self.code_path + '/configure.ac')
            if os.path.isfile(configure_path):
                c_mtime = os.path.getmtime(configure_path)
            else:
                c_mtime = 0.0

            # rerun autoconf if needed
            if c_mtime < ac_mtime:
                sh(['autoconf'], cwd=self.code_path)
                sh(['automake'], cwd=self.code_path)
                c_mtime = os.path.getmtime(configure_path)

            # reconfigure if needed

            if build_mtime < c_mtime:
                shutil.rmtree(self.build_path)
                os.makedirs(self.build_path)
                sh([configure_path] + get_configure_args(self.proj_name),
                   cwd=self.build_path)

            # build
            out('Building project \'{0}\''.format(self.proj_name))
            sh(['make', 'all', '-j{0}'.format(get_config_cpu_cores(self.proj_name))],
               cwd=self.build_path)

        elif self.build_type == BuildType.CMAKE:
            # cmake project

            os.makedirs(self.build_path, exist_ok=True)

            cmd = ['cmake', self.code_path]
            out(cmd)
            sh(cmd, cwd=self.build_path)

            out('Building project \'{0}\''.format(self.proj_name))
            sh(['make', 'all', '-j{0}'.format(get_config_cpu_cores(self.proj_name))],
               cwd=self.build_path)

        elif self.build_type == BuildType.QMAKE:
            # qmake project
            os.makedirs(self.paths.build_path, exist_ok=True)

            cmd = 'qmake \'{0}\''.format(self.code_path)
            out(cmd)

            # work around the issues with qmake out-of-source builds
            # In short, only directories at the same level are supported
            code_dir = '.{0}_codedir'.format(self.proj_name)
            sh(['ln', '-fs', self.code_path, '../' + code_dir],
               cwd=self.paths.build_path)

            sh(['qmake', '../{0}'.format(code_dir)], cwd=self.paths.build_path)

            out('Building project \'{0}\''.format(self.proj_name))
            sh(['make', 'all', '-j{0}'.format(get_config_cpu_cores(self.proj_name))],
               cwd=self.paths.build_path)

        elif self.build_type == BuildType.MAKEFILE:
            # Simple makefile project. Rebuild everything on any update in the
            # source tree

            # Get modification time of the build directory, create if it does
            # not exist
            if os.path.isdir(self.build_path):
                build_mtime = get_dir_mtime(self.build_path)
            else:
                os.makedirs(self.build_path)
                build_mtime = 0

            c_mtime = get_dir_mtime(self.code_path)

            if (build_mtime < c_mtime):
                out('Building project \'{0}\''.format(self.proj_name))

                shutil.rmtree(self.build_path)
                shutil.copytree(self.code_path, self.build_path)

                sh(['make', 'all', '-j{0}'.format(get_config_cpu_cores(self.proj_name))],
                   cwd=self.build_path)
        else:
            # No makefile -- nothing to build, only package. We expect that
            # debian/rules will have enough information
            out('... (no Makefile)')

    def clean(self):
        out('Cleaning project \'{0}\''.format(self.proj_name))

        if os.path.isdir(self.build_path):
            shutil.rmtree(self.build_path)

        if os.path.isdir(self.build_pkg_path):
            files = os.listdir(self.build_pkg_path)
            for f in files:
                if (re.search(r'\.deb$', f) or
                        re.search(r'\.changes$', f) or
                        re.search(r'\.build$', f) or
                        re.search(r'\.dsc$', f)):
                    os.remove(os.path.join(self.build_pkg_path, f))

    def reconf(self):
        out('Reconfiguring project \'{0}\''.format(self.proj_name))

        if self.build_type == BuildType.AUTOTOOLS:
            sh(['autoreconf'], cwd=self.code_path)
        elif self.build_type == BuildType.CMAKE:
            sh(['cmake', '.'], cwd=self.code_path)

    def check_build(self, do_check=True):
        if not do_check:
            return

        out('Checking project \'{0}\''.format(self.proj_name))

        if self.build_type != BuildType.NONE:
            # launch make check
            mkpath = os.path.join(self.build_path, 'Makefile')
            if os.path.exists(mkpath):
                mk = open(mkpath).read()
                if re.search(r'\bcheck:', mk):
                    sh(['make', 'check', '-j{0}'.format(get_config_cpu_cores(self.proj_name))],
                       cwd=self.build_path)
                else:
                    out('... (no check rule)')
            else:
                out('... (no Makefile)')

            # sh(['make', 'distcheck'], cwd=self.build_path)
        else:
            out('... (no Makefile)')

    def find_debian_folder(self):
        embedded_packaging_dir = get_config_embedded_packaging_dir(self.proj_name)
        if embedded_packaging_dir is not None:
            embedded_packaging_dir = os.path.join(self.code_path, embedded_packaging_dir)

        candidate_paths = [
            ('embedded_packaging_dir', embedded_packaging_dir),
            ('packaging', os.path.join(self.pkg_path, 'debian')),
            ('code', os.path.join(self.code_path, 'debian')),
        ]

        for name, debian_path in candidate_paths:
            if debian_path is None or not os.path.isdir(debian_path):
                continue

            out('Debian dir in {0} repo: {1}'.format(name, debian_path))
            return debian_path

        return None

    def extract_changelog_version(self, deb_folder):
        if deb_folder is None:
            out('ERROR: debian folder could not be found')
            sys.exit(1)

        changelog_path = os.path.join(deb_folder, 'changelog')
        if not os.path.exists(changelog_path):
            out('ERROR: could not extract debian changelog')
            sys.exit(1)
        for line in open(changelog_path).readlines():
            if line:
                m = re.match(r'^\s*([\w_+-.]+)\s*\(([\w_.:+~]+)(?:-([\w_.~+:]+))?\)',
                             line)
                if not m:
                    out('ERROR: could not match changelog line: \'{0}\''.format(
                        line))
                    sys.exit(1)
                name = m.group(1)
                ver = m.group(2)
                deb_ver = m.group(3)

                # strip epoch
                if ':' in ver:
                    epoch, sep, ver = ver.rpartition(':')

                return (name, ver, deb_ver)
        out('ERROR: could not match any changelog line')
        sys.exit(1)

    # Imports debian directory for a project extracted to ext_tar_path. Exits
    # on failure
    def import_debian_dir(self, tar_file, ext_tar_path):
        # Debian config folder is not distributed

        ext_tar_debian_path = os.path.join(ext_tar_path, 'debian')

        debian_path = self.find_debian_folder()

        if debian_path is not None:
            if os.path.exists(ext_tar_debian_path):
                out("WARN: Debian dir comes with source package too. " +
                    "Overwriting")
                shutil.rmtree(ext_tar_debian_path)

            shutil.copytree(debian_path, ext_tar_debian_path)
            return

        if os.path.isdir(ext_tar_debian_path):
            out("WARN: Debian dir is distributed with the source package")
        else:
            # No debian config folder exists -> create one and fail
            sh(['dh_make', '-f', tar_file], cwd=ext_tar_path)
            build_pkg_debian_path = os.path.join(self.build_pkg_path, 'debian')
            shutil.copytree(ext_tar_debian_path, build_pkg_debian_path)

            out("ERROR: Please update the debian configs at {0}".format(
                build_pkg_debian_path))
            sys.exit(1)

    # Finds the distributable tar.gz archive created by the make dist rule.
    # All tar.gz files within the build path are loosely matched with the
    # project name. The file which matches the largest number of words in the
    # projects name is selected.
    #
    # Returns None on failure
    def find_dist_tgz(self):
        tgzs = os.listdir(self.build_path)
        tgzs = [tgz for tgz in tgzs if tgz.endswith('.tar.gz') or
                tgz.endswith('.tar.xz')]
        tgzs.sort()  # don't depend on file order returned by listdir

        if len(tgzs) == 0:
            return None
        if len(tgzs) == 1:
            return tgzs[0]

        basenames = {os.path.splitext(tgz)[0] for tgz in tgzs}
        if len(basenames) == 1:
            return tgzs[0]

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

        if max_score == 0:
            return None

        return max_tgz

    ''' Creates a distributable by using make dist for autotools or makefile
        projects or exporting the current git work tree
        Returns a tuple containing the following data:
            base - the name of the project
            version - the version of the project
            ext - the format of the archive
            dist_file - the distributable tarball
    '''
    def make_distributable_make_dist(self):
        out('Using make dist packager')
        sh(['make', 'dist'], cwd=self.build_path)

        dist_file = self.find_dist_tgz()

        if dist_file is None:
            out("ERROR: Could not find distributable package (searched {})".format(self.proj_name))
            out("ERROR: Candidate files in {}: {}".format(self.build_path,
                                                          ' '.join(os.listdir(self.build_path))))
            sys.exit(1)

        m = re.match(r'(^.*-[^-]*)\.(tar\.(?:gz|xz))$', dist_file, re.I)
        if not m:
            out('ERROR: could not parse the filename of ' +
                'an archive \'{0}\''.format(dist_file))
            sys.exit(1)

        base, version, _ = \
            self.extract_changelog_version(self.find_debian_folder())
        tar_base = m.group(1)
        ext = m.group(2)
        dist_file = os.path.join(self.build_path, dist_file)
        return (base, version, tar_base, ext, dist_file)

    def make_distributable_git_archive(self):
        out('Using git packager')

        base, version, _ = \
            self.extract_changelog_version(self.find_debian_folder())
        tar_base = base + '-' + version

        dist_file = os.path.join(self.code_path, tar_base + '.tar.gz')

        if os.path.isfile(os.path.join(self.code_path, '.gitmodules')):
            dist_file_tar = os.path.join(self.code_path, tar_base + '.tar')

            sh(['git', 'archive', '--worktree-attributes',
                '--prefix=' + tar_base + '/', 'HEAD',
                '-o', dist_file_tar],
               cwd=self.code_path)

            sh(['git', 'submodule', 'foreach', '--recursive',
                f"git archive --worktree-attributes --prefix={tar_base + '/$path/'} " +
                "--output=$sha1.tar HEAD && " +
                f"tar --concatenate --file={os.path.abspath(dist_file_tar)} $sha1.tar && rm $sha1.tar"],
                cwd=self.code_path)

            # will automatically remove dist_file_tar and create dist_file
            sh(['gzip', '-f', dist_file_tar], cwd=self.code_path)
        else:
            sh(['git', 'archive', '--worktree-attributes',
                '--prefix=' + tar_base + '/', 'HEAD', '--format=tar.gz',
                '-o', dist_file],
               cwd=self.code_path)

        return (base, version, tar_base, 'tar.gz', dist_file)

    # Checks the project makefile for dist target
    def does_makefile_contain_dist_target(self):
        f = open(os.path.join(self.code_path, "Makefile"))
        for l in f:
            if l.startswith("dist:"):
                return True
        return False

    def make_distributable(self, use_dist=False):
        dist_method = get_config_dist_method(self.proj_name)
        if dist_method not in [None, 'git', 'autotools', 'makefile']:
            out('ERROR: Unsupported distribution method {}'.format(dist_method))
            sys.exit(1)

        # Make a distributable archive
        if not use_dist:
            if not self.vcs_type == VcsType.GIT:
                out('ERROR: Must create distributable package when not using git sources')
                sys.exit(1)
            return self.make_distributable_git_archive()

        if dist_method == 'autotools' or \
                (dist_method is None and self.build_type == BuildType.AUTOTOOLS):
            return self.make_distributable_make_dist()

        if dist_method == 'makefile' or \
                (self.build_type == BuildType.MAKEFILE and
                 self.does_makefile_contain_dist_target()):
            return self.make_distributable_make_dist()

        if dist_method == 'git' or \
                (dist_method is None and self.vcs_type == VcsType.GIT):
            return self.make_distributable_git_archive()

        out('ERROR: VCS and project type not supported')
        sys.exit(1)

    def get_pkgver_dirname(self, version, arch):
        if arch is None:
            return version
        return f"{version}_{arch}"

    def package(self, do_source=False, do_check=True, use_dist=False, arch=None):
        out('Packaging project \'{0}\''.format(self.proj_name))

        base, version, tar_base, ext, dist_file = self.make_distributable(use_dist=use_dist)

        out('File: {0}'.format(dist_file))
        out('Name: {0}; version: {1}'.format(base, version))
        out('Tar-dir: {0}'.format(tar_base))

        self.build_pkgver_path = os.path.join(self.build_pkg_path,
                                              self.get_pkgver_dirname(version, arch))
        tar_file = '{0}/{1}_{2}.orig.{3}'.format(self.build_pkgver_path, base,
                                                 version, ext)
        tar_path = os.path.join(self.build_pkgver_path, tar_base)

        # create a clean build dir
        if os.path.isdir(self.build_pkgver_path):
            shutil.rmtree(self.build_pkgver_path)
        os.makedirs(self.build_pkgver_path)

        # Move the distributable to the destination directory and cleanly
        # extract it
        shutil.move(dist_file, tar_file)
        sh(['tar', '-xf', tar_file, '-C', self.build_pkgver_path],
           cwd=self.build_pkgver_path)

        # Check if successful
        if not os.path.isdir(tar_path):
            out("ERROR: Failed to extract distributable archive to " + tar_path)
            sys.exit(1)

        # Import debian config folder
        self.import_debian_dir(tar_file, tar_path)

        # Make debian package
        self.debuild(tar_path, do_source, do_check, arch)

    # Returns arguments for dpkg package signing utility
    def get_key_args(self):
        key = get_config_debian_sign_key(self.proj_name)
        if key is None:
            return ['-us', '-uc']
        return ['-k' + key]

    # Runs debuild in the tar_path directory
    def debuild(self, tar_path, do_source, do_check, arch):
        key_args = self.get_key_args()

        num_cores = get_config_cpu_cores(self.proj_name)

        cmd = ['debuild']
        if True:
            cmd.append('--prepend-path=/usr/lib/ccache')

        build_options = [
            f'parallel={num_cores}',
        ]
        build_profiles = []
        if not do_check:
            build_options += ['nocheck', 'noinsttest', 'nodoc']
            build_profiles += ['nocheck', 'noinsttest', 'nodoc']

        cmd += [
            '-eDEB_BUILD_OPTIONS=' + ' '.join(build_options),
            '--no-lintian'
        ]
        if build_profiles:
            cmd += [
                '-eDEB_BUILD_PROFILES=' + ' '.join(build_profiles),
            ]

        if arch is not None:
            cmd += [f'-a{arch}']

        if do_source is True:
            r = sh(cmd + ['-S', '-sa'] + key_args,
                   cwd=tar_path)
        else:
            r = sh(cmd + ['-sa'] + key_args, cwd=tar_path)
        if r != 0:
            out("ERROR: Building project {0} failed".format(self.proj_name))
            sys.exit(1)

    def clean_path(self, path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path)

    def compute_dsc_filename(self, name, version, deb_version):
        return '{0}_{1}-{2}.dsc'.format(name, version, deb_version)

    def package_pristine(self, do_source=False, use_pbuilder=False, bare=False):
        if not use_pbuilder:
            out("Packaging pristine sources")
        else:
            out("Packaging pristine sources with pbuilder")
        deb_dir = os.path.join(self.code_path, 'debian')

        # check is deb_dir exists
        if not os.path.isdir(deb_dir):
            out("ERROR: No debian directory for project \'{0}\'".format(
                self.proj_name))
            sys.exit(1)

        (name, version, deb_version) = self.extract_changelog_version(deb_dir)

        self.build_pkgver_path = os.path.join(self.build_pkg_path, version)

        build_path = self.build_pkgver_path
        src_build_path = build_path + '_source'

        key_args = self.get_key_args()

        if do_source or use_pbuilder:
            self.clean_path(src_build_path)

            dsc_filename = self.compute_dsc_filename(name, version, deb_version)

            if bare:
                filename_glob = '../{0}_{1}.orig.tar.*'.format(name, version)
                orig_tars = glob.glob(os.path.join(self.code_path, filename_glob))

                out('Found the following tags matching {}:'.format(filename_glob))
                for path in orig_tars:
                    out(path)

                if len(orig_tars) == 0:
                    out("ERROR: no original tars found and bare was requested")
                    sys.exit(1)

                out('Packaging bare sources without VCS')
                sh(['dpkg-source', '-b', '.'], cwd=self.code_path)
                dsc_path = os.path.join(self.code_path, '..', dsc_filename)
            else:
                sh(['gbp', 'buildpackage', '--git-pristine-tar',
                    '--git-export-dir=' + src_build_path,
                    '-S', '-sa'] + key_args, cwd=self.code_path)
                dsc_path = os.path.join(src_build_path, dsc_filename)

            if use_pbuilder:
                self.clean_path(build_path)

                out("Using dsc: \'{0}\'".format(dsc_path))
                if not os.path.isfile(dsc_path):
                    out("ERROR: Could not find .dsc file")
                    sys.exit(1)

                sh(['sudo', 'pbuilder', 'build',
                    '--buildplace', self.paths.pbuilder_workdir_path,
                    '--basetgz', self.paths.pbuilder_tgz,
                    '--mirror', self.paths.pbuilder_mirror
                    ] + get_pbuilder_othermirror_opt(
                        self.paths.pbuilder_othermirror) + [
                    '--aptcache', self.paths.pbuilder_cache_path,
                    '--components', 'main',
                    '--buildresult', build_path,
                    dsc_path], cwd=self.paths.build_pbuilder_path)

        else:
            self.clean_path(build_path)
            sh(['gbp', 'buildpackage', '--git-pristine-tar',
                '--git-export-dir=', build_path, '-sa'] + key_args,
               cwd=self.code_path)

    def get_latest_pkgver(self):
        versions = []
        for d in os.listdir(self.build_pkg_path):
            d = os.path.join(self.build_pkg_path, d)
            if os.path.isdir(d):
                versions.append(d)

        return max(versions, key=os.path.getmtime)

    def install(self):
        # Install the package(s)
        if self.build_pkgver_path is None:
            self.build_pkgver_path = self.get_latest_pkgver()

        # TODO: switch to fnmatch
        sh('pkg=$(echo *.deb); /usr/lib/x86_64-linux-gnu/libexec/kf5/kdesu -t -c "dpkg -i $pkg"',
           cwd=self.build_pkgver_path)

    def debinstall(self):
        if self.build_pkgver_path is None:
            self.build_pkgver_path = self.get_latest_pkgver()

        # Install the package(s)
        debs = os.listdir(self.build_pkgver_path)
        for deb in debs:
            if deb.endswith('.deb'):
                shutil.copyfile(os.path.join(self.build_pkgver_path, deb),
                                os.path.join(self.paths.archive_path, deb))
        sh(['./reload'], cwd=self.paths.archive_path)


def get_projects_in_dir(path, filename):
    if not os.path.isdir(path):
        return []

    if glob.glob(path + "/*.dsc"):
        debian_projects = []

        for child_fn in os.listdir(path):
            child_path = os.path.join(path, child_fn)
            if not os.path.isdir(child_path):
                continue

            child_debian_path = os.path.join(child_path, 'debian')
            if not os.path.isdir(child_debian_path):
                continue

            debian_projects += [(child_path, filename + '_' + child_fn)]

        return debian_projects
    return [(path, filename)]


def get_available_projects(dirs):
    # get the list of available projects
    available_projects = []
    for d in dirs:
        try:
            project_fns = os.listdir(d)
        except Exception:
            continue

        for fn in project_fns:
            path = os.path.join(d, fn)
            available_projects += get_projects_in_dir(path, fn)

    return available_projects


def print_available_projects(project_dirs, deb_project_dirs):
    out("Available projects: ")
    for d, p in get_available_projects(project_dirs):
        out('\'{0}\' in directory \'{1}\''.format(p, d))

    out("")
    out("Available projects for pristine builds:")
    for d, p in get_available_projects(deb_project_dirs):
        out('\'{0}\' in directory \'{1}\''.format(p, d))


class Action(enum.Enum):
    CLEAN = 1
    FULL_CLEAN = 2
    BUILD = 3
    PACKAGE = 4
    PACKAGE_SOURCE = 5
    INSTALL = 6
    REINSTALL = 7
    DEBINSTALL = 8
    DEBREINSTALL = 9


class PbuilderAction(enum.Enum):
    CREATE = 1
    UPDATE = 2


def main():
    paths = PathConf()

    if (len(sys.argv) <= 1):
        out("ERROR: no name of project provided")
        print_available_projects(paths.project_dirs, paths.deb_project_dirs)
        sys.exit(1)

    action = None
    do_check = False
    do_build = False
    use_dist = False
    pristine = False
    pristine_bare = False
    use_pbuilder = False
    pbuilder_action = None

    parser = argparse.ArgumentParser(prog='make_all')
    parser.add_argument('projects', type=str, nargs='*',
                        help="Projects to build")
    parser.add_argument('--build', action='store_true', default=False,
                        help='Builds the source tree')
    parser.add_argument('--clean', action='store_true', default=False,
                        help='Cleans the source tree')
    parser.add_argument('--full-clean', action='store_true', default=False,
                        help='Cleans the source tree and reconfigures the source tree ' +
                        '(if possible)')
    parser.add_argument('--package', action='store_true', default=False,
                        help='Builds the source tree and creates a binary package')
    parser.add_argument('--package-source', action='store_true', default=False,
                        help='Builds the source tree and creates a source package')
    parser.add_argument('--install', action='store_true', default=False,
                        help='Builds the source tree, creates a binary package and installs it ' +
                        'into both the system and to the local repository')
    parser.add_argument('--reinstall', action='store_true', default=False,
                        help='Reinstalls most recently built binary packages both to the system ' +
                        'and to the local repository')
    parser.add_argument('--debinstall', action='store_true', default=False,
                        help='Builds the source tree, creates a binary package and installs it ' +
                        'into to the local repository')
    parser.add_argument('--use-dist', action='store_true', default=False,
                        help='Build distributable package using make dist or equivalent when ' +
                        'packaging')
    parser.add_argument('--arch', type=str, default=None,
                        help='Override the architecture for packaging')
    parser.add_argument('--debreinstall', action='store_true', default=False,
                        help='Reinstalls most recently built binary packages to the local ' +
                        'repository')
    parser.add_argument('--pristine', action='store_true', default=False,
                        help='Enables pristine mode. Can only be used with --package, ' +
                        '--package-source, --install, --reinstall, --debinstall, --debreinstall ' +
                        'options')
    parser.add_argument('--pristine-bare', action='store_true', default=False,
                        help='Enables bare pristine mode. This is the same as --pristine except ' +
                        'that bare tar.gz archives will be used as a source base. This option ' +
                        'can only be used with --package, --package-source, --install, ' +
                        '--reinstall, --debinstall, --debreinstall options')
    parser.add_argument('--use-pbuilder', action='store_true', default=False,
                        help='Enables pbuilder mode. Can only be enabled when --pristine or ' +
                        '--pristine-bare options are enabled. --create-pbuilder must be executed ' +
                        'at least once before using this option')
    parser.add_argument('--create-pbuilder', action='store_true', default=False,
                        help='Creates a pbuilder environment. Must not be used with any other ' +
                        'build-related option. --pbuilder-dist selects the distribution')
    parser.add_argument('--update-pbuilder', action='store_true', default=False,
                        help='Updates a pbuilder environment. Must not be used with any other ' +
                        'build-related option. --pbuilder-dist selects the distribution')
    parser.add_argument('--pbuilder-dist', type=str, default=None,
                        help='Selects the pbuilder distribution')
    args = parser.parse_args()

    if args.build:
        action = Action.BUILD
        do_build = True
    if args.clean:
        action = Action.CLEAN
        do_check = True
    if args.full_clean:
        action = Action.FULL_CLEAN
    if args.package:
        action = Action.PACKAGE
    if args.package_source:
        action = Action.PACKAGE_SOURCE
    if args.install:
        action = Action.INSTALL
    if args.reinstall:
        action = Action.REINSTALL
    if args.debinstall:
        action = Action.DEBINSTALL
    if args.debreinstall:
        action = Action.DEBREINSTALL

    if args.use_dist:
        use_dist = True
    if args.pristine:
        pristine = True
    if args.pristine_bare:
        pristine = True
        pristine_bare = True

    if args.use_pbuilder:
        use_pbuilder = True

    if args.create_pbuilder:
        pbuilder_action = PbuilderAction.CREATE
    elif args.update_pbuilder:
        pbuilder_action = PbuilderAction.UPDATE

    if args.pbuilder_dist is not None:
        paths.set_pbuilder_dist(args.pbuilder_dist)

    if pbuilder_action is not None:
        if pristine or pristine_bare or action is not None:
            out("ERROR: --create-pbuilder must not be used along with any "
                "other options")
            sys.exit(1)
        out("Creating pbuilder environment. Please wait...")

        os.makedirs(paths.pbuilder_tgz_path, exist_ok=True)
        os.makedirs(paths.pbuilder_workdir_path, exist_ok=True)
        os.makedirs(paths.pbuilder_cache_path, exist_ok=True)
        os.makedirs(paths.build_pbuilder_path, exist_ok=True)

        actions = {
            PbuilderAction.CREATE: 'create',
            PbuilderAction.UPDATE: 'update'
        }

        sh(['sudo', 'pbuilder', actions[pbuilder_action],
            '--distribution', paths.pbuilder_distribution,
            '--debootstrapopts', '--variant=buildd',
            '--debootstrapopts', '--keyring',
            '--debootstrapopts', '/etc/apt/trusted.gpg',
            '--buildplace', paths.pbuilder_workdir_path,
            '--basetgz', paths.pbuilder_tgz,
            '--mirror', paths.pbuilder_mirror,
            ] + get_pbuilder_othermirror_opt(paths.pbuilder_othermirror) + [
            '--aptcache', paths.pbuilder_cache_path,
            '--components', 'main'], cwd=paths.build_pbuilder_path)
        sys.exit(0)

    if pristine:
        if action in [Action.CLEAN, Action.FULL_CLEAN, Action.BUILD]:
            out("ERROR: --pristine and --pristine_bare must not be used along with --clean, "
                "--full_clean and --build")
            sys.exit(1)
        paths.project_dirs = paths.deb_project_dirs
        paths.build_pkg_path = paths.build_deb_pkg_path

    # check received projects
    checked_projects = []

    for proj in args.projects:
        if proj == '.':
            cwd = os.getcwd()
            proj = os.path.basename(cwd)
            checked_projects.append((cwd, proj))
            if os.path.dirname(os.path.dirname(cwd)) != paths.root_path:
                out("ERROR: . project name can only be used in project root")
                sys.exit(1)
            continue

        if '/' in proj:
            project_root, proj = proj.split('/')
            project_dirs = [os.path.join(paths.root_path, project_root)]
        else:
            project_dirs = paths.project_dirs
        available_projects = get_available_projects(project_dirs)
        for d, p in available_projects:
            if p == proj:
                checked_projects += [(d, p)]
                break

    for path in paths.build_path, paths.build_pkg_path:
        os.makedirs(path, exist_ok=True)

    if len(checked_projects) > 0:
        out("Found projects: ")
        for d, p in checked_projects:
            out('\'{0}\' in directory \'{1}\''.format(p, d))
    else:
        out("ERROR: Project not found. Abort. ")
        sys.exit(1)

    if action is None:
        out("WARN: Action not specified. Defaulting to compile+package+install")
        action = Action.INSTALL

    # do work
    if action == Action.FULL_CLEAN:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            pr.reconf()
            pr.clean()

    elif action == Action.CLEAN:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            pr.clean()

    elif action == Action.BUILD:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            pr.build()
            pr.check_build(do_check)

    elif action == Action.PACKAGE:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            if pristine:
                pr.package_pristine(use_pbuilder=use_pbuilder, bare=pristine_bare)
            else:
                pr.build(do_build)
                pr.check_build(do_build and do_check)
                pr.package(do_check=do_check, use_dist=use_dist, arch=args.arch)
                out('Packages placed in: ' + pr.build_pkgver_path)

    elif action == Action.PACKAGE_SOURCE:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            if pristine:
                pr.package_pristine(do_source=True, use_pbuilder=use_pbuilder, bare=pristine_bare)
            else:
                pr.build(do_build)
                pr.check_build(do_build and do_check)
                pr.package(do_source=True, do_check=do_check, use_dist=use_dist,
                           arch=args.arch)
                out('Packages placed in: ' + pr.build_pkgver_path)

    elif action == Action.INSTALL:
        for d, p in checked_projects:
            pr = Project(paths, p, d)

            if pristine:
                pr.package_pristine(use_pbuilder=use_pbuilder, bare=pristine_bare)
            else:
                pr.build(do_build)
                pr.check_build(do_build and do_check)
                pr.package(do_check=do_check, use_dist=use_dist, arch=args.arch)

            out("Installing project: \'{0}\'".format(p))
            pr.install()
            pr.debinstall()

    elif action == Action.REINSTALL:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            out("Installing project: \'{0}\'".format(p))
            pr.install()
            pr.debinstall()

    elif action == Action.DEBINSTALL:
        for d, p in checked_projects:
            pr = Project(paths, p, d)

            if pristine:
                pr.package_pristine(use_pbuilder=use_pbuilder, bare=pristine_bare)
            else:
                pr.build()
                pr.check_build(do_check)
                pr.package(do_check=do_check, use_dist=use_dist, arch=args.arch)

            out("Installing project: \'{0}\'".format(p))
            pr.debinstall()

    elif action == Action.DEBREINSTALL:
        for d, p in checked_projects:
            pr = Project(paths, p, d)
            out("Installing project: \'{0}\'".format(p))
            pr.debinstall()

    else:
        out("ERROR: Wrong action! \'{0}\'".format(action))
        sys.exit(1)

    out("Success!")


if __name__ == '__main__':
    main()
