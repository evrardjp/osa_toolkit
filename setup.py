from setuptools import setup

setup(
    name='osa_toolkit',
    version='0.1',
    py_modules=['osa_toolkit'],
    install_requires=[
        'Click',
        'click-log',
        'pyyaml'
    ],
    entry_points='''
        [console_scripts]
        update_arr=release.py:update_arr
    ''',
)
