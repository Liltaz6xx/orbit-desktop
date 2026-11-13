# Contributing to ORBIT Desktop

Open a GitHub issue with a short description of the change or reproduction steps. Include the ORBIT version, Windows version and the output of the system checker after removing personal paths and identifiers. Keep SQLite files, voice weights and conversation content out of reports and pull requests.

Run the tests from the project root before opening a pull request.

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q main.py orbit scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

The automated tests use a temporary SQLite database and simulated Windows actions. For an interface change, describe what you checked in the native window. For a change to Windows tools, add a test for the approved command and nearby phrases that should be rejected.
