""" Make the whole thing pip installable """
from setuptools import setup

setup(
    name='osa_toolkit',
    version='0.1',
    py_modules=['release'],
    install_requires=[
        'Click',
        'click-log',
        'GitPython',
        'requirements-parser',
        'ruamel.yaml',
        'semver'
    ],
    entry_points='''
        [console_scripts]
        check-global-requirements=release.py:check_global_requirement_pins
        bump-upstream-sources=release.py:bump_upstream_sources
        update-role-files=release.py:update_role_files
        bump-ansible-role-requirements=release.py:bump_arr
        bump-oa-release-number=release.py:bump_oa_release_number
        update-os-release-file=release.py:update_os_release_file
    ''',
)
