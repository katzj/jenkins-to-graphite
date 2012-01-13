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
import json
import logging
import optparse
import os
import sys
import socket
import time
import urllib2

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
            opener.addheaders = [(("Authorization", "Basic " + base64.encodestring("%s:%s" % (self.user, self.password))))]
            urllib2.install_opener(opener)
            self._opener = opener

        return self._opener

    def get_data(self, url):
        """Get the data from jenkins at @url and return it as a dictionary"""

        try:
            f = self.opener.open("%s/%s/api/json" % (self.base_url, url))
            response = f.read()
            f.close()
            data = json.loads(response)
        except Exception, e:
            logging.warn("Unable to get jenkins response for url %s: %s" %(url, e))
            return {}

        return data

class GraphiteServer(object):
    def __init__(self, server, port):
        self.server = server
        self.port = int(port)

        self.data = {}

    def add_data(self, key, value):
        self.data[key] = value

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
        except Exception as e:
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

    (opts, args) = parser.parse_args()

    if not opts.graphite_server or not opts.jenkins_url:
        print >> sys.stderr, "Need to specify graphite server and jenkins url"
        sys.exit(1)

    return opts

def main():
    opts = parse_args()
    jenkins = JenkinsServer(opts.jenkins_url, opts.jenkins_user,
                            opts.jenkins_password)
    graphite = GraphiteServer(opts.graphite_server, opts.graphite_port)

    queue_info = jenkins.get_data("/queue")
    executor_info = jenkins.get_data("/computer")

    graphite.add_data("jenkins.build_queue", len(queue_info.get("items", [])))
    graphite.add_data("jenkins.total_executors", executor_info.get("totalExecutors", 0))
    graphite.add_data("jenkins.busy_executors", executor_info.get("busyExecutors", 0))
    graphite.add_data("jenkins.free_executors",
                      executor_info.get("totalExecutors", 0) -
                      executor_info.get("busyExecutors", 0))

    graphite.send()

if __name__ == "__main__":
    main()
