#!/bin/bash

set -e -u

#directory layout configuration
root_path=/home/exec/code/my/
archive_path=/home/exec/downloads/apt/

rel_code_path="code"
rel_build_path="build"
rel_build_pkg_path="build_packaging"
rel_pkg_path="packaging"
rel_log_path="log"

log_ext="build_log"

all_projects="compiz-panel-session
              libbpk
              libpeach-core
              libsimdpp
              libpeach-audio
              dupremove
              paswman
              cppreference-doc
              pkan-bundle
              libgwtmm
              sim-gas
              "

#first arg carries the project name
build()
{
    echo "Configuring project '$1'"

    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"

    #check for autoconf
    if [ -f "$code_path/configure" -o -f "$code_path/configure.ac" ]
    then
        #get modification time of the build directory, create if it does not exist
        if [ -e "$build_path" ]
        then
            build_mtime=$(stat --format "%Y" "$build_path")
        else
            mkdir -p "$build_path"
            build_mtime=0
        fi

        ac_mtime=$(stat --format=%Y "$code_path/configure.ac")
        if [ -f "$code_path/configure" ]
        then
            c_mtime=$(stat --format=%Y "$code_path/configure")
        else
            c_mtime=0
        fi

        #rerun autoreconf if needed
        if [ $c_mtime -lt $ac_mtime ]
        then
            pushd "$code_path" > /dev/null
            autoreconf
            popd > /dev/null
            c_mtime=$(stat --format=%Y "$code_path/configure")
        fi

        #reconfigure if needed
        if [ $build_mtime -lt $c_mtime ]
        then
            rm -rf "$build_path"
            mkdir -p "$build_path"

            pushd "$build_path" > /dev/null
            $code_path/configure #&> $log_file
            popd > /dev/null
        fi

        #build
        echo "Building project '$1'"

        pushd "$build_path" > /dev/null
        make all -j4 #&> $log_file
        popd > /dev/null

    else
        #simple makefile project. Rebuild everything on any update in the source tree

        #get modification time of the build directory, create if it does not exist
        if [ -d "$build_path" ]
        then
            build_mtime=$(find -L "$build_path"  -not -path "./.git*" -exec stat --format "%Y" \{} \; | sort -n -r | head -1)
        else
            mkdir -p "$build_path"
            build_mtime=0
        fi

        c_mtime=$(find -L "$code_path"  -not -path "./.git*" -exec stat --format "%Y" \{} \; | sort -n -r | head -1)

        if [ $build_mtime -lt $c_mtime ]
        then
            echo "Building project '$1'"

            rm -rf "$build_path"
            mkdir -p "$build_path"
            cp -rTL "$code_path" "$build_path"

            pushd "$build_path" > /dev/null
            make all -j4 #&> $log_file
            popd > /dev/null
        fi
    fi
}

#first arg carries the project name
clean()
{
    echo "Cleaning project '$1'"

    #compute required paths
    build_path="$root_path/$rel_build_path/$1"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"
    code_path="$root_path/$rel_code_path/$1"

    if [ -e $build_path ]
    then
        rm -rf "$build_path"
    fi

    if [ -e $build_pkg_path ]
    then
        debs=$(find $build_pkg_path -maxdepth 1 -iname "*.deb" -o -iname "*.changes" -o -iname "*.build" -o -iname "*.dsc")
        if [ "$debs" ]
        then
            rm -f $debs
        fi
    fi
}

#first arg carries the project name
reconf()
{
    echo "Reconfiguring project '$1'"

    #compute required paths
    code_path="$root_path/$rel_code_path/$1"

    pushd "$code_path" > /dev/null
    autoreconf
    popd > /dev/null
}

#first arg carries the project name
check_build()
{
    echo "Checking project '$1'"

    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    build_path="$root_path/$rel_build_path/$1"

    #cd to build dir and lauch make check
    pushd "$build_path" > /dev/null
    make check -j2 #&> $log_file
    #make distcheck #&> $log_file
    popd > /dev/null
}

#first arg carries the project name
#second arg: if 'and_source', a source package is build. Other values are ignored
package()
{
    echo "Packaging project '$1'"

    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"
    pkg_path="$root_path/$rel_pkg_path/$1"

    #make distributable
    pushd "$build_path" > /dev/null
    make dist #&> $log_file
    popd > /dev/null

    #find the resulting distributable tar file
    dist_file=$(find "$build_path" -iname "*$1*.tar.gz")

    if [ "$dist_file" == "" ]
    then
        echo "ERROR: Could not find distributable package"
        exit 1
    fi

    base=$(expr match "$dist_file" '.*/\([^/]*\)-[0-9.]*\.tar\.gz' )
    version=$(expr match "$dist_file" '.*-\([0-9.]*\)\.tar\.gz' )

    tar_file=$build_pkg_path/$base"_"$version.orig.tar.gz
    tar_path=$build_pkg_path/$base-$version

    #make the debian dir
    mkdir -p $build_pkg_path

    #move the distributable to the destination directory and cleanly extract it
    mv $dist_file $tar_file
    if [ -e $tar_path ]
    then
        rm -rf $tar_path
    fi
    tar -xzf $tar_file -C $build_pkg_path/

    #check if successful
    if [ ! -e $tar_path ]
    then
        echo "ERROR: Failed to extract distributable archive to $tar_path"
        exit 1
    fi

    #check for debian config folder, create one using dh_make if not existing
    if [ ! -e $tar_path/debian ]
    then
        #debian config folder is not distributed
        if [ -e $pkg_path/debian ]
        then
            #found one in packaging dir
            cp -rL $pkg_path/debian $tar_path/
        elif [ -e $code_path/debian ]
        then
            #found one in code dir
            cp -rL $code_path/debian $tar_path/
        else
            #no debian config folder exists -> create one and fail
            pushd $tar_path > /dev/null
            dh_make -f $tar_file
            popd > /dev/null

            cp -R $tar_path/debian $build_pkg_path/

            echo "ERROR: Please update the debian configs at $build_pkg_path/debian"
            exit 1
        fi
    fi

    #clear the directory
    pushd $build_pkg_path > /dev/null
    find . -iname "*.deb" -exec rm -f '{}' \;
    popd > /dev/null

    #make debian package
    pushd $tar_path > /dev/null
    debuild --no-lintian --build-hook="$root_path/copy_build_files.sh $build_path" -sa -k0x0374452d #&> $log_file

    if [ "${2+xxx}" == "and_source" ]
    then
        debuild --no-lintian --build-hook="$root_path/copy_build_files.sh $build_path" -S -sa -k0x0374452d #&> $log_file
    fi
    popd > /dev/null
}

install()
{
    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"

    #install the package(s)
    pushd "$build_pkg_path" > /dev/null
    deb_packages=$(echo *.deb)
    gksu "dpkg -i $deb_packages"
    popd > /dev/null
}

debinstall()
{
    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"
    build_pkg_path="$root_path/$rel_build_pkg_path/$1"

    #install the package(s)
    pushd "$build_pkg_path" > /dev/null
    deb_packages=$(echo *.deb)
    cp -f $deb_packages $archive_path
    pushd "$archive_path" > /dev/null
    ./reload
    popd > /dev/null
    popd > /dev/null
}

#shows the available options to the stderr
show_help()
{
    echo "Usage:" >&2
    echo "" >&2
    echo "make_all.sh [action] [projects ...] " >&2
    echo "" >&2
    echo "Actions:" >&2;
    echo "" >&2
    echo " --build -b - builds the source tree" >&2
    echo "" >&2
    echo " --clean -n - cleans the build tree" >&2
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
    echo "Defaulting to compile+package+install on all packages"
    projects_to_build=$all_projects
    action="install"
else
    action="i"

    while [ "$#" -gt "0" ]
    do
        case $1 in
            -c|--clean) action="clean";;
            -f|--full_clean) action="full_clean";;
            -b|--build) action="build";;
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
        echo "Defaulting to compile+package+install"
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
    full_clean)
        for p in $projects_to_build
        do
            reconf $p
            clean $p
        done
        ;;
    clean)
        for p in $projects_to_build
        do
            clean $p
        done
        ;;
    build)
        for p in $projects_to_build
        do
            build $p
            check_build $p
        done
        ;;
    package)
        for p in $projects_to_build
        do
            build $p
            check_build $p
            package $p
        done
        ;;
    package_source)
        for p in $projects_to_build
        do
            build $p
            check_build $p
            package $p "and_source"
        done
        ;;
    install)
        for p in $projects_to_build
        do
            build $p
            check_build $p
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
            build $p
            check_build $p
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
