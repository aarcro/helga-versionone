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

On py26 you'll need to pip install ordereddict


Settings to Add
---------------

You'll need these in your settings.py

 * __VERSIONONE_URL__ Url to your instance endpoint.
 * __VERSIONONE_AUTH__ Two element tuple: (Username, Password). Not needed with Oauth.
 * __VERSIONONE_CR_FIELDS__ List of custom fields that hold codereview links.
 * __VERSIONONE_READONLY__ (Default: True) Set to False to allow writing to V1.
 * __VERSIONONE_OAUTH_CLIENT_ID__  From your Oauth client.
 * __VERSIONONE_OAUTH_CLIENT_SECRET__ From your Oauth client.
 * __VERSIONONE_OAUTH_ENABLED__ (Default: False) Set to True to enable Oauth.

Commands
========

Anything in () is optional. *emphatic* terms should be replaced.

 1. __alias [(lookup) *nick* | set | remove]__ - Lookup an alias, or set/remove your own
 1. __oauth__ - Configures your oauth tokens
 1. __review *issue* (!)*text*__ - Lookup, append, or set (when using !) codereview field (alias: cr)
 1. __take *ticket-id*__ - Add yourself to the ticket\'s Owners
 1. __tasks *ticket-id* (add *title*)__ - List tasks for ticket, or add one
 1. __teams [add | remove | (list)] *teamname*__ - add, remove, list team(s) for the channel (alias: team)
 1. __tests *ticket-id* (add *title*)__ - List tests for ticket, or add one
 1. __user (*nick*)__ - Lookup V1 user for an ircnick
