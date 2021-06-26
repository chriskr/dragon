#!/usr/bin/env python

from dragon.common import __version__ as VERSION

try:
    from setuptools import setup, find_packages
    addl_args = dict(
        packages=find_packages(),
        entry_points={
            'console_scripts': [
                'dragon = dragon.dragon:main_func'
            ],
        },
    )

except ImportError:
    from distutils.core import setup
    addl_args = dict(
        packages=[
            'dragon',
        ],
    )

setup(
    name='dragon',
    version=VERSION.decode(),
    url='http://bitbucket.org/scope/dragon/',
    author='Christian Krebs, Rune Halvorsen, Jan Borsodi',
    author_email='chrisk@opera.com, runeh@opera.com, jborsodi@opera.com',
    data_files=[('dragon', ['dragon/favicon.ico']),
                ('dragon', ['dragon/device-favicon.png',
                            'dragon/folder.png',
                            'dragon/file.png'])],
    description='An HTTP proxy for Opera Dragonfly development',
    long_description=open("README.md").read(),
    **addl_args
)
