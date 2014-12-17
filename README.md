helga-versionone
================

VersionOne Plugin for the helga chatbot.

Installation
============

Using pip
---------

pip install --allow-external elementtree --allow-unverified elementtree helga-versionone

If you're wondering what the ``--allow-external elementtree``
and ``--allow-unverified elementree`` lines are about:
This program relies upon the
`Python SDK released by the VersionOne team <https://github.com/versionone/VersionOne.SDK.Python>`
(albeit, an unofficial distribution of it), and that SDK relies upon elementree
which is unavailable through verified/local PyPI sources.


Settings to Add
---------------

You'll need these in your settings.py

 * __VERSIONONE_URL__ Url to your instance endpoint
 * __VERSIONONE_AUTH__ Two element tuple: (Username, Password)
