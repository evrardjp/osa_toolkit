Release.py
==========

Release tooling for OpenStack-Ansible.

If you're not using default workspace folder (/tmp/workdir), you should define it in all the commands.

Bumping master
--------------

Steps:

1. Checkout to master (not detached)
1. Suggest upper constraints pin changes:
   ``check-global-requirements``
1. Update Upstream Projects:
   ```bash
    bump-upstream-sources --commit
    #update-role-files --comit
   ```
1. Git review

Releasing master milestone
--------------------------

Steps:

1. Go to OA folder
1. Ensure you're master (not detached)
1. Freeze ansible-role-requirements by doing:
   ```bash
    bump-ansible-role-requirements
    bump-oa-release-number --version=17.0.0b1 --commit
   ```
1. git review in OA
1. Wait for it to merge.
1. Ensure you're still at the right sha in your workspace folder (detached or not).
1. Emit release commit by doing (it will be based on checked out sha)
   ```bash
    update-os-release-file --branch=queens --version=17.0.0b1 --commit
   ```
1. Review in your release folder and git review
1. Unfreeze by git revert

Doing a stable release
----------------------

Steps:

1. Go to OA folder
1. Ensure you're at the head of your branch you want to release, or at the right sha.
   ```
   update-os-release-file --branch=pike --version=16.0.2 --commit
   ```
1. Go to release folder in workspace
1. Review and git review
1. Take review change id
   ```bash
   export release_changeid=$(git log HEAD^..HEAD | awk '/Change-Id/ {print $2}')
   ```
1. Ensure you're into OA folder, in a branch you can commit to (tracking what's needed)
1. Bump files
   ```bash
   bump-ansible-role-requirements
   bump-oa-release-number --version=auto
       export next_release= ...
   check-global-requirements
   bump-upstream-sources --commit
   #update-role-files --comit
   ```
1. Review OpenStack-Ansible folder and each of the roles.

Maturity.py
===========

This toolkit will manage the maturity matrix that appears on openstack-ansible
docs.

If you're not using default workspace folder (/tmp/maturity), you should define it in all the commands.

For now, only one command is implemented:
update-role-maturity-matrix (--commit)
