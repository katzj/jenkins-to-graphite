# Overview
jenkins-to-graphite is a Python script to connect via HTTP Basic authentication
to a Jenkins instance, collect some basic metric data, and feed it into [Graphite](http://graphite.readthedocs.io/en/stable/)

# Requirements
* Python 2.6 or higher

# Usage
Run with `--help` to see possible options.

Most likely you will want to use something like `cron` to schedule this to
run at an interval that suits your needs.

# Author
Jeremy Katz <katzj@hubspot.com>
