import os
import glob


def get_ext_modules(): # poetry build / backend setuptools
    import pybind11
    import numpy as np
    from setuptools import Extension
    from Cython.Build import cythonize

    # sources = glob.glob("**/*.pyx", recursive=True) # **/*.pyx 会搜索当前目录及其所有子目录下的 .pyx 文件
    current_dir = os.path.abspath(os.getcwd())

    extensions = [
        # Extension(
        #     name="bt_sdk.core.rpc.client", 
        #     sources=["bt_sdk/core/rpc/client.pyx"],
        #     include_dirs=[np.get_include(), current_dir],
        #     language="c++",
        #     extra_compile_args=["-O3", "-std=c++11"],
        #         # "-Wno-unused-function",
        #         # "-Wno-unused-variable",
        #         # "-Wno-unused-but-set-variable",
        #         # "-Wno-unused-parameter",
        #         # "-Wno-sign-compare", # O3 极致优化，C++11 标准
        # ),
        # # Pybind11 Extension
        # Extension(
        #     "bt_sdk.core.lib.adj_factor",  
        #     sources=[
        #         "bt_sdk/core/lib/factor/src/factor.cpp",    
        #         "bt_sdk/core/lib/factor/pybind_factor.cpp",  
        #     ],
        #     include_dirs=[
        #         pybind11.get_include(), 
        #         np.get_include(),     
        #         "bt_sdk/core/lib/factor/include", 
        #     ],
        #     language="c++",              
        #     extra_compile_args=["-std=c++17", "-O3"], 
        # )
    ]
    
    compiler_directives={
        'language_level': "3",       # 使用 Python 3 语法
        'boundscheck': False,        # 关闭数组越界检查（提升性能）
        'wraparound': False,         # 关闭负索引支持（提升性能）
        'initializedcheck': False,   # 关闭内存视图初始化检查
        'cdivision': True,           # 开启 C 级别除法（不检查除零，极快）
    }

    ext_modules = cythonize(
        extensions,
        compiler_directives=compiler_directives,
        annotate=False # .html 文件，方便查看代码是否实现C 级加速
        )
    return ext_modules


if __name__ == "__main__":
    from setuptools import setup, find_packages

    setup(
        name="bt_protocol",
        packages=find_packages(),
        include_package_data=True, 
        ext_modules=get_ext_modules()
    )
