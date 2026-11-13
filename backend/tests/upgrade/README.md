# Saved old databases

`databases/<tag>.sqlite` is a database from each earlier release (v0.1.0, v0.1.1, v0.2.0, v0.2.1, v0.3.0, v0.4.0, v0.5.0, v0.5.1, v0.6.0, v0.7.0, v0.8.0, v0.9.0-beta.1). Each was made by that release's own code, through that release's own API, filled with a small made-up household: an admin (`sam`, password `correct horse battery`), then what that release had (a second login, ingredients, stock, a shopping list with ticked lines, recipes, a plan with meals and tubs, a batch-cook session, a second person).

`make_databases.py` and `fill_one.py` made them (a dev script: never run by the tests, not shipped). They stand for real old installs, so they are never re-made casually: re-making changes every file, and a database made from today's code would not be an old one. Add a new file when a release ships; do not change the old ones.

`tests/test_upgrade_from_tags.py` upgrades a copy of each to the newest layout. `upgraded_09_db` (conftest.py) is the 0.9.0-beta.1 database kept for later tests.
