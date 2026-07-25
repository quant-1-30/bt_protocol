import os
import glob


def get_ext_modules():
    """Return the list of Cython/pybind11 Extension modules to build.

    Auto-discovers top-level ``*.pyx`` files so new extensions only need to be
    dropped into the package tree. When nothing is found we return an empty list
    *without* invoking ``cythonize`` -- calling ``cythonize([])`` is wasteful and
    still requires Cython/numpy/pybind11 to be importable at build time.
    """
    pyx_sources = glob.glob("**/*.pyx", recursive=True)
    if not pyx_sources:
        return []

    import numpy as np
    from setuptools import Extension
    from Cython.Build import cythonize

    current_dir = os.path.abspath(os.getcwd())

    extensions = [
        Extension(
            name=os.path.splitext(os.path.relpath(p, current_dir))[0].replace(os.sep, "."),
            sources=[p],
            include_dirs=[np.get_include(), current_dir],
            language="c++",
            extra_compile_args=["-O3", "-std=c++17"],
        )
        for p in pyx_sources
    ]

    compiler_directives = {
        'language_level': "3",       # Python 3 syntax
        'boundscheck': False,        # disable bounds checking (perf)
        'wraparound': False,         # disable negative indexing (perf)
        'initializedcheck': False,   # disable memoryview init checks
        'cdivision': True,           # C-level division (no zero-division check)
    }

    return cythonize(
        extensions,
        compiler_directives=compiler_directives,
        annotate=False,
    )


if __name__ == "__main__":
    from setuptools import setup, find_packages

    setup(
        name="bt_protocol",
        packages=find_packages(),
        include_package_data=True,
        ext_modules=get_ext_modules(),
    )