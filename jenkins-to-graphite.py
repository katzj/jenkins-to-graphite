#!/usr/bin/python
#
# Send various statistics about jenkins to graphite
#
# Jeremy Katz <katzj@hubspot.com>
# Copyright 2012, HubSpot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import base64
import logging
import optparse
import os
import sys
import socket
import time
import urllib2

try:
    # this should be available in any python 2.6 or newer
    import json
except:
    try:
        # simplejson is a good replacement on 2.5 installs
        import simplejson as json
    except:
        print "FATAL ERROR: can't find any json library for python"
        print "Please install simplejson, json, or upgrade to python 2.6+"
        sys.exit(1)
#end json import


class JenkinsServer(object):
    def __init__(self, base_url, user, password):
        self.base_url = base_url
        self.user = user
        self.password = password

        self._opener = None

    @property
    def opener(self):
        """Creates a urllib2 opener with basic auth for talking to jenkins"""
        if self._opener is None:
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
            if self.user or self.password:
                opener.addheaders = [(("Authorization", "Basic " + base64.encodestring("%s:%s" % (self.user, self.password))))]
            urllib2.install_opener(opener)
            self._opener = opener

        return self._opener

    def get_raw_data(self, url):
        """Get the data from jenkins at @url and return it as a dictionary"""

        try:
            f = self.opener.open("%s/%s" % (self.base_url, url))
            response = f.read()
            f.close()
            data = json.loads(response)
        except Exception, e:
            logging.warn("Unable to get jenkins response for url %s: %s" % (url, e))
            return {}

        return data

    def get_data(self, url):
        return self.get_raw_data("%s/api/json" % url)


class GraphiteServer(object):
    def __init__(self, server, port, prefix):
        self.server = server
        self.port = int(port)
        self.prefix = prefix.rstrip('.')

        self.data = {}

    def add_data(self, key, value):
        self.data["%s.%s" % (self.prefix, key)] = value

    def _data_as_msg(self):
        msg = ""
        now = time.time()
        for (key, val) in self.data.items():
            msg += "%s %s %s\n" % (key, val, now)
        return msg

    def send(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.server, self.port))
            s.sendall(self._data_as_msg())
#            print self._data_as_msg()
            s.close()
        except Exception, e:
            logging.warn("Unable to send msg to graphite: %s" % (e,))
            return False

        return True


def parse_args():
    parser = optparse.OptionParser()
    parser.add_option("", "--graphite-server",
                      help="Host name of the server running graphite")
    parser.add_option("", "--graphite-port",
                      default="2003")
    parser.add_option("", "--jenkins-url",
                      help="Base url of your jenkins server (ex http://jenkins.example.com")
    parser.add_option("", "--jenkins-user",
                      help="User to authenticate with for jenkins")
    parser.add_option("", "--jenkins-password",
                      help="Password for authenticating with jenkins")

    parser.add_option("", "--jobs",
                      help="Jobs view to monitor for success/failure")
    parser.add_option("", "--prefix", default="jenkins",
                      help="Graphite metric prefix")
    parser.add_option("", "--label", action="append", dest="labels",
                      help="Fetch stats applicable to this node label. Can bee applied multiple times for monitoring more labels.")

    (opts, args) = parser.parse_args()

    if not opts.graphite_server or not opts.jenkins_url:
        print >> sys.stderr, "Need to specify graphite server and jenkins url"
        sys.exit(1)

    return opts


def main():
    opts = parse_args()
    jenkins = JenkinsServer(opts.jenkins_url, opts.jenkins_user,
                            opts.jenkins_password)
    graphite = GraphiteServer(opts.graphite_server, opts.graphite_port,
                              opts.prefix)

    executor_info = jenkins.get_data("computer")
    queue_info = jenkins.get_data("queue")
    build_info_min = jenkins.get_raw_data("view/All/timeline/data?min=%d&max=%d" % ((time.time() - 60) * 1000, time.time() * 1000))
    build_info_hour = jenkins.get_raw_data("view/All/timeline/data?min=%d&max=%d" % ((time.time() - 3600) * 1000, time.time() * 1000))

    graphite.add_data("queue.size", len(queue_info.get("items", [])))

    graphite.add_data("builds.started_builds_last_minute", len(build_info_min.get("events", [])))
    graphite.add_data("builds.started_builds_last_hour", len(build_info_hour.get("events", [])))

    graphite.add_data("executors.total", executor_info.get("totalExecutors", 0))
    graphite.add_data("executors.busy", executor_info.get("busyExecutors", 0))
    graphite.add_data("executors.free",
                      executor_info.get("totalExecutors", 0) -
                      executor_info.get("busyExecutors", 0))

    nodes_total = executor_info.get("computer", [])
    nodes_offline = [j for j in nodes_total if j.get("offline")]
    graphite.add_data("nodes.total", len(nodes_total))
    graphite.add_data("nodes.offline", len(nodes_offline))
    graphite.add_data("nodes.online", len(nodes_total) - len(nodes_offline))

    if opts.labels:
        for label in opts.labels:
            label_info = jenkins.get_data("label/%s" % label)
            graphite.add_data("labels.%s.jobs.tiedJobs" % label, len(label_info.get("tiedJobs", [])))
            graphite.add_data("labels.%s.nodes.total" % label, len(label_info.get("nodes", [])))
            graphite.add_data("labels.%s.executors.total" % label, label_info.get("totalExecutors", 0))
            graphite.add_data("labels.%s.executors.busy" % label, label_info.get("busyExecutors", 0))
            graphite.add_data("labels.%s.executors.free" % label,
                              label_info.get("totalExecutors", 0) -
                              label_info.get("busyExecutors", 0))

    if opts.jobs:
        builds_info = jenkins.get_data("/view/%s" % opts.jobs)
        jobs = builds_info.get("jobs", [])
        ok = [j for j in jobs if j.get("color", 0) == "blue"]
        fail = [j for j in jobs if j.get("color", 0) == "red"]
        warn = [j for j in jobs if j.get("color", 0) == "yellow"]
        graphite.add_data("jobs.total", len(jobs))
        graphite.add_data("jobs.ok", len(ok))
        graphite.add_data("jobs.fail", len(fail))
        graphite.add_data("jobs.warn", len(warn))

    graphite.send()

if __name__ == "__main__":
    main()
