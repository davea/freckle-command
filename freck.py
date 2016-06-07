#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import base64
import getpass
import logging
import optparse
import os
import re
import sys
import urllib2

VERSION = "1.1.0" # http://semver.org/

CONFIG_KEYS = set([ "subdomain", "user", "token", "project", "tags" ])

# Exit with an error message
def fail(template, **values):
    program_name = sys.argv[0].split('/')[-1]
    print >>sys.stderr, program_name + ": " + template.format(**values)
    sys.exit(1)

# Check we have a new enough Python to run this script
if sys.version_info < (2, 6):
    fail("This script requires Python 2.6 or later")

# Older pythons don’t include the json module, and we would prefer
# to fail with a more informative error message so we load it after
# we have checked the Python version.
import json

# A class that encapsulates the config file handling and API calls
class Freckle(object):
    def __init__(self):
        self._load_config()
        self.url_base = "https://{subdomain}.letsfreckle.com/api/".format(
            subdomain=self.config["subdomain"])
        self._load_projects()
        self._load_tags()

    def _generate_config(self):
        """Generate configuration file interactively; called if we don’t have one yet.
        """
        print "Type the subdomain associated with your Freckle account, e.g. mysociety"
        subdomain = raw_input("subdomain: ")

        print "Type the email address you used to register with Freckle"
        email = raw_input("email: ")
        if '@' not in email:
            fail("That’s not an email address")

        password = getpass.getpass("password: ")

        self.url_base = "https://{subdomain}.letsfreckle.com/api/".format(subdomain=subdomain)
        try:
            r = self.api("user", "api_auth_token", user=email, password=password)
        except urllib2.HTTPError:
            fail("Failed to connect to {subdomain}.letsfreckle.com\nCheck your details and try again.",
                subdomain=subdomain)
        token = r["user"]["api_auth_token"]

        self.config = {
            "subdomain": subdomain,
            "user": email,
            "token": token,
        }

        self._load_projects()
        self.list_projects()

        print "Type your current project. You may leave this blank"
        project = raw_input("project: ")
        if project not in self.projects:
            print
            print "WARNING: The project '{project}' does not exist.".format(project=project)
            print "If this is a mistake, edit ~/.freck and correct it."
            print "To create this project, use the --create option next time you run freck."
            print
        self.config["project"] = project

        print "Type tags to include by default. You may leave this blank"
        self.config["tags"] = raw_input("tags: ")
        print

        self._save_config()

    def _load_config(self):
        """Load configuration file.
        """
        self.config_file = os.path.join(os.environ["HOME"], ".freck")
        if os.path.isfile(self.config_file):
            self.just_generated_config = False
        else:
            self._generate_config()
            self.just_generated_config = True
            return

        self.config = {}
        with open(self.config_file, 'r') as f:
            line_number = 0
            for line in f:
                line_number += 1

                # Remove comments and leading/trailing whitespace
                line = re.sub(r"#.*", "", line).strip()
                if not line: continue

                mo = re.match(r"([^:]+):\s*(.*)", line)
                if not mo:
                    fail("Syntax error in ~/.freck at line {line_number}: {line}",
                        line_number=line_number, line=line)
                key = mo.group(1)
                value = mo.group(2)

                if key not in CONFIG_KEYS:
                    fail("Unrecognised key '{key}' in ~/.freck at line {line_number}",
                        key=key, line_number=line_number)
                self.config[key] = value

    def _save_config(self):
        with open(self.config_file, 'w') as f:
            f.write("".join([
                "{key}: {value}\n".format(key=key, value=value)
                for key, value in self.config.items()
            ]))

        print "Your settings have been saved in {config_file}".format(
            config_file=self.config_file)
        print "You may change them at any time by editing this file."

    def api(self, *path, **kwargs):
        """Make a call to the API.
        """
        url = self.url_base + "/".join(path) + ".json"
        json_data = None if "data" not in kwargs else json.dumps(kwargs["data"])
        headers = { "Content-Type": "application/json" }
        if "user" in kwargs:
            headers["Authorization"] = "Basic " + base64.b64encode(
                kwargs["user"] + ":" + kwargs["password"])
        else:
            headers["X-FreckleToken"] = self.config["token"]

        logging.debug("Requesting %s with payload %r", url, json_data)
        r = urllib2.urlopen(urllib2.Request(url, json_data, headers))

        s = r.read()
        if s.strip() == "": return None
        return json.loads(s)

    def _load_projects(self):
        """Load the list of projects.
        """
        if hasattr(self, "projects"):
            # Projects are already loaded
            return

        self.projects = {}
        for p in self.api("projects"):
            project = p["project"]
            self.projects[project["name"]] = project["id"]

    def proj(self, project_name):
        if project_name is None:
            project_name = self.config.get("project")
            if not project_name:
                fail("No project name specified, and no default")
        return project_name

    def create_project(self, project_name):
        """Create a new project with the specified name.
        Returns True if a new project was created.
        """
        project_name = self.proj(project_name)
        if project_name in self.projects: return False
        self.api("projects", data={"project": {"name": project_name}})
        return True

    def list_projects(self):
        """Print a list of all projects.
        """
        print "Projects for {subdomain}.letsfreckle.com:".format(
            subdomain=self.config["subdomain"])

        for project in sorted(self.projects.iterkeys()):
            if project == self.config.get("project"):
                print "* " + project.encode("utf-8")
            else:
                print "  " + project.encode("utf-8")
        print

    def _load_tags(self):
        """Load the list of tags.
        """
        if hasattr(self, "tags"):
            # Tags are already loaded
            return

        self.tags = {}
        for t in self.api("tags"):
            tag = t["tag"]
            self.tags[tag["name"]] = tag["id"]

    def list_tags(self):
        """Print a list of all tags.
        """
        print "Tags for {subdomain}.letsfreckle.com:".format(
            subdomain=self.config["subdomain"])

        for tag in self.tags:
            if tag == self.config.get("tag"):
                print "* " + tag.encode("utf-8")
            else:
                print "  " + tag.encode("utf-8")
        print

    def create_entry(self, time, description=None, tags=None, project_name=None, date=None, user=None):
        """Create a new time-tracking entry.
        """
        project_name = self.proj(project_name.decode("utf-8"))
        if project_name not in self.projects:
            if project_name == self.config["project"]:
                # The default project does not exist
                fail("Default project '{project_name}' does not exist.\nEdit ~/.freck to specify one that does.",
                    project_name=project_name)

            # Not the default project
            fail("Project '{project_name}' does not exist.\nYou can create it by specifying --create, or list the existing projects by specifying --list-projects.",
                project_name=project_name)

        if tags is None: tags = self.config.get("tags")
        hashtags = " ".join(["#{0}".format(tag) for tag in tags.split(",")])

        data = {
            "user": user or self.config["user"],
            "minutes": time,
            "project_id": self.projects[project_name],
            "description": " ".join([hashtags, description]),
            "allow_hashtags": True,
        }
        if date: data["date"] = date

        try:
            self.api("entries", data={"entry": data})
        except urllib2.HTTPError, e:
            fail("Failed to create entry '{time}' for project {project_name}: {message}",
                time=time, project_name=project_name, message=str(e))

if __name__ == '__main__':
    # Parse the command line
    parser = optparse.OptionParser(usage="%prog [options] time_spent description/tags ...")
    parser.add_option("", "--version",
                    action="store_true",
                    help="print version number and exit")

    parser.add_option("-l", "--list-projects",
                    action="store_true",
                    help="list all available projects")

    parser.add_option("-L", "--list-tags",
                    action="store_true",
                    help="list all available tags")

    parser.add_option("-t", "--tags",
                    action="store",
                    help="additional tags, overriding the default if any")
    parser.add_option("-d", "--date",
                    action="store",
                    help="the date this task was done, if not today: yyyy-mm-dd")
    parser.add_option("-u", "--user",
                    action="store",
                    help="email address of user to record time for, if not you")

    parser.add_option("-p", "--project",
                    action="store",
                    help="the name of the project. If you have specified a default you can miss this out")
    parser.add_option("-c", "--create",
                    action="store_true",
                    help="create the project if it does not exist")

    parser.add_option("-v", "--verbose",
                    action="store_true",
                    help="print detailed logging messages")
    parser.add_option("-s", "--silent",
                    action="store_true",
                    help="print no informational messages")

    (options, args) = parser.parse_args()

    if options.version:
        print VERSION
        sys.exit(0)

    # Configure logging
    if options.verbose and options.silent:
        parser.error("Cannot specify both --verbose and --silent")
    log_level = logging.INFO
    if options.verbose: log_level = logging.DEBUG
    if options.silent:  log_level = logging.WARN
    logging.basicConfig(level=log_level, format=" * %(message)s")


    # The main program
    if options.list_projects:
        if args:
            parser.error("Unexpected argument following --list-projects: " + args[0])
        Freckle().list_projects()
        sys.exit(0)

    if options.list_tags:
        if args:
            parser.error("Unexpected argument following --list-tags: " + args[0])
        Freckle().list_tags()
        sys.exit(0)

    freckle = Freckle()
    done_something = False
    if options.create:
        if freckle.create_project(options.project):
            logging.info("Created new project: %s", options.project)
            done_something = True
        else:
            logging.debug("The project %s already exists", options.project)

    if args:
        time = args[0]
        freckle.create_entry(time, ", ".join(args[1:]), options.tags,
            options.project, options.date, options.user)
        logging.info("Recorded %s against project %s", time, freckle.proj(options.project))
        done_something = True

    if not done_something and not freckle.just_generated_config:
        logging.info("Nothing to do. Did you mean to specify a time? Use -h for help.")
