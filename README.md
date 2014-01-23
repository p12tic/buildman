Overview
--------

This repository contains several scripts that I (povilas@radix.lt) use to
automate proper building, packaging and signing of projects that I develop or
customize.

The general layout that I use is as follows (note that it can be easily
customized in make_all.py):

~/code/my -- root directory, referred to as {root} below

{root}/make_all.py

The driver script. It _must_ be in the root directory.

{root}/checkouts/{project}/
{root}/local/{project}/

Locations of the project sources

{root}/checkouts_packaging/{project}

Location of project packaging information. Only debian packaging is supported
-- each project contains a debian/ directory with the packaging information.

{root}/build/{project}/

Location where a particular project is built. Only out-of-source builds are
supported.

{root}/build_packaging/{project}/{project-version}

Location where project packaging is built. Each {project} directory may
contain several directories, tarballs and various other files for each version
of the project.


This is a personal project primarily for my own use. I reserve the right to
modify the published history.
