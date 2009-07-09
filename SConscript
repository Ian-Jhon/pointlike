# -*- python -*-
# @file SConscript
# @brief scons build specifications
#
# $Header: /nfs/slac/g/glast/ground/cvs/ScienceTools-scons/pointlike/SConscript,v 1.62 2009/06/04 20:30:51 glastrm Exp $
# Authors: Toby Burnett <tburnett@u.washington.edu>
# Version: pointlike-06-20-02

#specify package name, applications
package= 'pointlike'
apps   =['pointfit', 'pointfind', 'alignment']

# this part is standard: assume includes, a shareable lib, zero or more applications, a test program
Import('baseEnv')
Import('listFiles')
progEnv = baseEnv.Clone()
libEnv = baseEnv.Clone()

progEnv.Tool(package+'Lib')
libEnv.Tool(package+'Lib', depsOnly = 1)
lib = libEnv.SharedLibrary(package, listFiles(['src/*.cxx']))

swigEnv = progEnv.Clone()

swigEnv.Append(RPATH = swigEnv['LIBDIR'])
pyLib = swigEnv.LoadableModule('_pointlike','python/swig_setup.i')

progEnv.Tool('registerObjects', 
    package  = package, 
    includes = listFiles([package+'/*.h']),
    libraries= [lib, pyLib], 
    binaries = [progEnv.Program(name, listFiles(['src/%s/*.cxx'%name])) for name in apps], 
    testApps = [progEnv.Program('test_'+package, listFiles(['src/test/*.cxx']))],
    python = ['python/pointlike.py'],
 )
