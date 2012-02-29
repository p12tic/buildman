#!/bin/bash

set -e -u

#directory layout configuration
root_path=/home/exec/code/my/
archive_path=/home/exec/downloads/apt/

rel_code_path="code"
rel_build_path="build"
rel_debian_path="debian"
rel_log_path="log"

log_ext="build_log"

all_projects="compiz-panel-session
              libpeach-core 
              libpeach-sse
              libpeach-audio 
              dupremove 
              paswman 
              cppreference-doc
              pkan-bundle
              libgwtmm
              sim-gas
              "

#shows the available options to the stderr
show_help()
{
    echo "Usage:" >&2
    echo "" >&2
    echo "make_all.sh [action] [projects ...] " >&2
    echo "" >&2
    echo "Actions:" >&2;
    echo " --build -b - builds the source tree" >&2
    echo " --clean -n - cleans the build tree" >&2
    echo " --package -p - builds the source tree and creates a package" >&2
    echo " --install -i - builds the source tree and creates a package and installs it" >&2
    echo " --reinstall -I - reintalls already build packages" >&2
    echo " --help  - displays this text" >&2
}

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
    debian_path="$root_path/$rel_debian_path/$1"
    code_path="$root_path/$rel_code_path/$1"

    if [ -e $build_path ]
    then
        rm -rf "$build_path"
    fi

    if [ -e $debian_path ]
    then
        debs=$(find $debian_path -iname "*.deb")
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
package()
{
    echo "Packaging project '$1'"

    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"
    debian_path="$root_path/$rel_debian_path/$1"

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

    tar_file=$debian_path/$base"_"$version.orig.tar.gz
    tar_path=$debian_path/$base-$version

    #make the debian dir
    mkdir -p $debian_path
    
    #move the distributable to the destination directory and cleanly extract it
    mv $dist_file $tar_file
    if [ -e $tar_path ] 
    then
        rm -rf $tar_path
    fi
    tar -xzf $tar_file -C $debian_path/

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
        if [ -e $debian_path/debian ]
        then
            #found one in parent dir
            cp -rL $debian_path/debian $tar_path/
        elif [ -e $code_path/debian ]
        then
            #found one in code dir
            cp -rL $code_path/debian $tar_path/
        else
            #no debian config folder exists -> create one and fail
            pushd $tar_path > /dev/null
            dh_make -f $tar_file
            popd > /dev/null
            
            cp -R $tar_path/debian $debian_path/
            
            echo "ERROR: Please update the debian configs at $debian_path/debian"
            exit 1
        fi
    fi

    #clear the directory
    pushd $debian_path > /dev/null
    find . -iname "*.deb" -exec rm -f '{}' \;
    popd > /dev/null
    
    #make debian package
    pushd $tar_path > /dev/null
    debuild --no-lintian --build-hook="$root_path/copy_build_files.sh $build_path" -k0x0374452d #&> $log_file
    popd > /dev/null

}

install()
{
    #compute required paths
    log_file="$root_path/$rel_log_path/$1.$log_ext"
    code_path="$root_path/$rel_code_path/$1"
    build_path="$root_path/$rel_build_path/$1"
    debian_path="$root_path/$rel_debian_path/$1"

    #install the package(s)
    pushd "$debian_path" > /dev/null
    deb_packages=$(echo *.deb)
    gksu "dpkg -i $deb_packages"
    cp -f $deb_packages $archive_path
    popd > /dev/null
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
            -i|--install) action="install";;
            -I|--reinstall) action="reinstall";;
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

#export functions and variables that will be needed by xargs
export root_path
export rel_code_path
export rel_build_path
export rel_debian_path
export rel_log_path
export log_ext

export -f clean
export -f build
export -f reconf
export -f check_build
export -f package

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
    install)
        for p in $projects_to_build
        do
            build $p
            check_build $p
            package $p

            echo "Installing project: $p"
            install $p
        done
        ;;
    reinstall)
        for p in $projects_to_build
        do
            echo "Installing project: $p"
            install $p
        done
        ;;
    *)
        echo "ERROR: Wrong action $action !"
        exit 1;
        ;;
esac

echo "Success!"
