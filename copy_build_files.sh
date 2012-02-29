#!/bin/bash

set -e

if [ $# -lt 1 ]
then
    echo "Bad arguments"
    exit 1
fi

target_dir=$(pwd);

pushd $1 > /dev/null

obj_filelist=$(find -name "*.o" -o -name "*.lo" )
dep_filelist=$(find -name "*.Plo")
dir_list=$(find -type d )

#create .dirstamp files
for dir in $dir_list
do
    mkdir -p $target_dir/$dir
    touch $target_dir/$dir/.dirstamp
done

#create dummy dependency files
for file in $dep_filelist
do
    cp --parents "$file" "$target_dir"
    rfile="$target_dir/$file"
    #time=$(stat -c "%y" $rfile)
    echo "#dummy" > $rfile
    #touch -d "$time" $rfile
done

#copy objects
for file in $obj_filelist
do
    cp --parents "$file" "$target_dir"
done

popd > /dev/null
