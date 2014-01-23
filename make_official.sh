#!/bin/bash

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

set -e -u

#directory layout configuration
root_path=/home/exec/code/my/
archive_path=/home/exec/downloads/apt/

rel_build_pkg_path="build_packaging"
rel_pkg_path="checkouts_packaging"
rel_log_path="log"

log_ext="build_log"

all_projects="cppreference-doc
              "

#first arg carries the project name
#second arg: if 'and_source', a source package is build. Other values are ignored
package()
{
    echo "Packaging project '$1'"

    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"
    pkg_path="$root_path/$rel_pkg_path/$1"

    #build the package using git-buildpackage
    pushd "$pkg_path" > /dev/null

    changelog_line=$(cat "debian/changelog" | head -1)
    [[ $changelog_line =~ ^([^(]*?)\(([^)]*)\) ]]
    pkg=${BASH_REMATCH[1]}
    pkg=$(echo "$pkg" | sed 's/^ *//' | sed 's/ *$//')
    version=${BASH_REMATCH[2]}
    version=$(echo "$version" | sed 's/^ *//' | sed 's/ *$//')

    if [ "${2:-xxx}" == "and_source" ]
    then
        version="$version"_source
    fi

    pkg_name="$pkg"_"$version"
    pkg_path="$build_pkg_path/$pkg_name"

    rm -rf "$pkg_path"
    mkdir -p "$pkg_path"

    if [ "${2:-xxx}" == "and_source" ]
    then
        git-buildpackage --git-pristine-tar --git-export-dir="$pkg_path" -S -sa -k0x0374452d
    else
        git-buildpackage --git-pristine-tar --git-export-dir="$pkg_path" -sa -k0x0374452d
    fi

    popd > /dev/null
}

install()
{
    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"

    #install the package(s)
    pushd "$build_pkg_path" > /dev/null
    newest=$(ls -t1 | head -1)
    pushd "$newest" > /dev/null

    deb_packages=$(echo *.deb)
    gksu "dpkg -i $deb_packages"

    popd > /dev/null
    popd > /dev/null
}

debinstall()
{
    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"

    #install the package(s)
    pushd "$build_pkg_path" > /dev/null
    newest=$(ls -t1 | head -1)
    pushd "$newest" > /dev/null

    deb_packages=$(echo *.deb)
    cp -f $deb_packages $archive_path
    pushd "$archive_path" > /dev/null
    ./reload
    popd > /dev/null

    popd > /dev/null
    popd > /dev/null
}

#shows the available options to the stderr
show_help()
{
    echo "Usage:" >&2
    echo "" >&2
    echo "make_official.sh [projects ...] " >&2
    echo "" >&2
    echo "Actions:" >&2;
    echo "" >&2
    echo " --package -p - builds the source tree and creates a binary package" >&2
    echo "" >&2
    echo " --package_source -s - builds the source tree, creates a source and " >&2
    echo "   binary packages" >&2
    echo "" >&2
    echo " --install -i - builds the source tree, creates a binary package and" >&2
    echo "   installs it both to the system and to a local repository" >&2
    echo "" >&2
    echo " --reinstall -I - reintalls already built binary packages both to the" >&2
    echo "   system and to a local repository" >&2
    echo "" >&2
    echo " --debinstall -d - builds the source tree, creates a binary package " >&2
    echo "   and installs it only to a local repository" >&2
    echo "" >&2
    echo " --debreinstall -D - reintalls already built binary packages to a" >&2
    echo "   local repository" >&2
    echo "" >&2
    echo " --help  - displays this text" >&2
}

projects_to_build=""

#parse arguments
if [ $# -lt 1 ]
then
    echo "Defaulting to package+install on all packages"
    projects_to_build=$all_projects
    action="install"
else
    action="i"

    while [ "$#" -gt "0" ]
    do
        case $1 in
            -p|--package) action="package";;
            -s|--package_source) action="package_source";;
            -i|--install) action="install";;
            -I|--reinstall) action="reinstall";;
            -d|--debinstall) action="debinstall";;
            -D|--debreinstall) action="debreinstall";;
            --help) show_help; exit 1;;
            *)  projects_to_build="$projects_to_build $1";;
        esac
        shift
    done

    if [ "$action" == "i" ]
    then
        echo "Defaulting to package+install"
        action="install"
    fi

    #check project names
    for p in $projects_to_build
    do
        answer=$(echo "$all_projects" | awk "/^(.* )?$p( .*)?\$/")
        if [ "$answer" == "" ]
        then
            echo "ERROR: Wrong project '$p'"
            exit 1
        fi
    done
fi

#do work
case $action in
    package)
        for p in $projects_to_build
        do
            package $p
        done
        ;;
    package_source)
        for p in $projects_to_build
        do
            package $p "and_source"
        done
        ;;
    install)
        for p in $projects_to_build
        do
            package $p

            echo "Installing project: $p"
            install $p
            debinstall $p
        done
        ;;
    reinstall)
        for p in $projects_to_build
        do
            echo "Installing project: $p"
            install $p
            debinstall $p
        done
        ;;
    debinstall)
        for p in $projects_to_build
        do
            package $p

            echo "Installing project: $p"
            debinstall $p
        done
        ;;
    debreinstall)
        for p in $projects_to_build
        do
            echo "Installing project: $p"
            debinstall $p
        done
        ;;
    *)
        echo "ERROR: Wrong action $action !"
        exit 1;
        ;;
esac

echo "Success!"
