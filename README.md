# make_prefab_aar
A script for creating AAR files to hold ndk C/C++ libraries in prefabs for Android development

# make_protobuf-aar.py

While this file is specific to [the protobuf library](https://github.com/protocolbuffers/protobuf) it is meant to also be a template for making similar scripts for other projects. You have to specify some metadata at the top of the file and write a function to determine the version of the project you're compiling (this function could just return a constant if you want to manually set that value of course,) then the script should generate a working AAR with libraries for all 4 of the currently supported Android architectures. It will automatically detect static libraries and name them with -static appended. For example libprotobuf.so will be protobuf::protobuf libprotobuf.a will be protobuf::protobuf-static. 
- The script assumes you have an environment variable $ANDROID_NDK_HOME set to the path of the ndk you want to use. 
- The script assumes that there is a working configure script in place so you may need to run autogen.sh or something similiar prior to running it;
- If you you run the script with no arguments it will assume the parent of the folder it is in contains the library and place the completed AAR in this folder. for example the script could be in some_library/build-scripts it will run configure in the some_library folder and place the aar in the some_library folder. 
- '-i' specifies an input directory (where the library source is);
- '-o' specifies an output directory. 
- The -h flag will print out help information;
