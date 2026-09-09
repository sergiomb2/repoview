#!/usr/bin/env python3
# -*- mode: Python; indent-tabs-mode: nil; -*-
"""
Repoview is a small utility to generate static HTML pages for a repodata
directory, to make it easily browseable.

@author:    Konstantin Ryabitsev & contributors
@copyright: 2005 by Duke University, 2006-2007 by Konstantin Ryabitsev & co
@license:   GPLv2
"""
##
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# $Id$
#
# Copyright (C) 2005 by Duke University, http://www.duke.edu/
# Copyright (C) 2006 by McGill University, http://www.mcgill.ca/
# Copyright (C) 2007 by Konstantin Ryabitsev and contributors
# Author: Konstantin Ryabitsev <icon@fedoraproject.org>
#

__revision__ = '$Id$'

import os
import shutil
import sys
import time
import hashlib
import functools
from typing import Any, Dict, List, Optional, Sequence, Tuple
from bz2 import BZ2File
from gzip import GzipFile
from lzma import LZMAFile
from tempfile import mkstemp

try:
    import rpm  # type: ignore[import]
except ImportError as exc:
    raise ImportError('Repoview requires the "rpm" Python bindings.') from exc

from optparse import OptionParser

try:
    from genshi.template import TemplateLoader  # type: ignore[import]
except ImportError as exc:
    raise ImportError('Repoview requires the "genshi" package.') from exc

from xml.etree.ElementTree import fromstring, ElementTree, TreeBuilder

import sqlite3 as sqlite

try:
    import libcomps  # type: ignore[import]
except ImportError:
    libcomps = None  # type: ignore[assignment]

##
# Some hardcoded constants
#
PKGKID    = 'package.kid'
PKGFILE   = '%s.html'
GRPKID    = 'group.kid'
GRPFILE   = '%s.group.html'
IDXKID    = 'index.kid'
IDXFILE   = 'index.html'
RSSKID    = 'rss.kid'
RSSFILE   = 'latest-feed.xml'
ISOFORMAT = '%a, %d %b %Y %H:%M:%S %z'

VERSION = '0.7.1'
SUPPORTED_DB_VERSION = 10
DEFAULT_TEMPLATEDIR = '/usr/share/repoview/templates/default'

# High-level execution pipeline (mirrored by the inline "Phase" comments below):
#   1. Parse CLI arguments (main) and instantiate Repoview.
#   2. Locate repository assets, prepare output/state directories, build exclusion SQL.
#   3. Build group definitions (comps, RPM groups, letter groups) and render package pages.
#   4. Render aggregate views (group pages, index, optional RSS).
#   5. Persist incremental state and delete artifacts from previous runs.

def _mkid(text):
    """
    Make a web-friendly filename out of group names and package names.

    @param text: the text to clean up
    @type  text: str

    @return: a web-friendly filename
    @rtype:  str
    """
    text = text.replace('/', '.')
    text = text.replace(' ', '_')
    return text

def _humansize(num_bytes):
    """
    This will return the size in sane units (KiB or MiB).

    @param bytes: number of bytes
    @type  bytes: int

    @return: human-readable string
    @rtype:  str
    """
    if num_bytes < 1024:
        return f'{num_bytes:d} Bytes'
    num_bytes = int(num_bytes)
    kbytes = num_bytes // 1024
    if kbytes // 1024 < 1:
        return f'{kbytes:d} KiB'
    return f'{float(kbytes)/1024:0.1f} MiB'

def _compare_evra(one, two):
    """
    Comparison helper for sorting packages by EVR (Epoch, Version, Release).
    
    It adapts the tuple format for use with rpm.labelCompare.

    @param one: tuple of (e,v,r,a)
    @type  one: tuple
    @param two: tuple of (e,v,r,a)
    @type  two: tuple

    @return: -1, 0, 1
    @rtype:  int
    """
    # Use only (epoch, version, release) and convert epoch to string
    evr_one = (str(one[0]), one[1], one[2])
    evr_two = (str(two[0]), two[1], two[2])

    return rpm.labelCompare(evr_one, evr_two)

class Repoview:
    """
    The main controller class for Repoview.
    
    This class handles the entire workflow:
    1. initializing repository connections and state database,
    2. processing groups and packages,
    3. managing incremental builds via checksums,
    4. rendering templates using Genshi,
    5. and generating the final HTML output and RSS feeds.
    """

    def __del__(self):
        for entry in self.cleanup:
            if os.access(entry, os.W_OK):
                os.unlink(entry)

    def __init__(self, opts):
        """
        @param opts: OptionParser's opts
        @type  opts: OptionParser
        """
        # The constructor orchestrates the full build pipeline up front so that
        # later helper methods can assume all shared state (database handles,
        # exclusion SQL, template loaders, etc.) already exists.
        # The initialization order below mirrors the chronological order of a
        # repoview run: collect inputs → prepare filesystem → prepare state →
        # compute grouping metadata → render pages → persist state.
        # list of files to remove at the end of processing
        self.cleanup: List[str] = []
        self.opts    = opts
        # Honor the CLI-provided output directory name (defaults to "repoview")
        # but always treat it as a subdirectory of the repository root.
        self.outdir  = os.path.join(opts.repodir, opts.outdir)

        self.exclude    = '1=1'
        # Dictionary storing filename -> checksum mapping from the state database (previous run).
        # Used to determine if a file needs to be regenerated.
        self.state_data: Dict[str, str] = {}
        # Dictionary tracking packages processed in the current run to handle duplicates
        # and avoid re-processing. Maps pkgname -> pkg_tuple.
        self.written: Dict[str, Tuple[str, str, Optional[str]]] = {}

        self.groups: List[Sequence[Any]] = []
        self.letter_groups: List[Sequence[Any]] = []

        self.pconn: Optional[sqlite.Connection] = None # primary.sqlite
        self.oconn: Optional[sqlite.Connection] = None # other.sqlite
        self.sconn: Optional[sqlite.Connection] = None # state db

        # Phase 1: locate repository metadata, initialize database handles.
        self.setup_repo()
        # Phase 2: prepare filesystem targets and incremental build state.
        self.setup_outdir()
        self.setup_state_db()
        self.setup_excludes()

        if not self.groups:
            self.setup_rpm_groups()

        letters = self.setup_letter_groups()

        repo_data = {
                     'title':      opts.title,
                     'letters':    letters,
                     'my_version': VERSION
                    }
        # Template engine handles page rendering.  Each TemplateLoader instance can cache
        # compiled templates, so we keep dedicated loaders for packages and groups to
        # avoid cross-assignment of contextual attributes.
        group_kid = TemplateLoader(opts.templatedir)
        self.group_kid = group_kid

        pkg_kid = TemplateLoader(opts.templatedir)
        self.pkg_kid = pkg_kid

        count = 0
        # Phase 3: Iterate through all logical groups (explicit comps groups plus
        # auto-generated alphabetical "Letter" buckets).  Each iteration renders
        # the packages belonging to the group, wires them into group metadata, and
        # produces the HTML if any of the constituent checksums changed.
        for group_data in self.groups + self.letter_groups:
            (grp_name, grp_filename, grp_description, pkgnames) = group_data
            pkgnames.sort()

            group_data = {
                          'name':        grp_name,
                          'description': grp_description,
                          'filename':    grp_filename,
                          }

            # Package pages double as a cache warm-up for group pages: the call returns
            # summary tuples used on the group listing while also writing/refining the
            # individual package HTML files.
            packages = self.do_packages(repo_data, group_data, pkgnames)

            if not packages:
                # Empty groups are ignored
                del self.groups[count]
                continue

            count += 1

            group_data['packages'] = packages

            checksum = self.mk_checksum(repo_data, group_data)
            if self.has_changed(grp_filename, checksum):
                # write group file
                self.say(f'Writing group {grp_filename}\n')
                self.group_kid.group_data = group_data
                outfile = os.path.join(self.outdir, grp_filename)

                tmpl = self.group_kid.load(GRPKID)

                stream = tmpl.generate(group_data=group_data, repo_data=repo_data)
                with open(outfile, "w", encoding="utf-8") as handle:
                    handle.write(stream.render('xhtml', doctype='xhtml-strict'))

        # Phase 4: Build aggregated views (latest packages list, index page, optional RSS).
        latest = self.get_latest_packages()
        repo_data['latest'] = latest
        repo_data['groups'] = self.groups

        checksum = self.mk_checksum(repo_data)
        if self.has_changed('index.html', checksum):
            # Write index.html and rss feed (if asked)
            self.say('Writing index.html...')
            idx_kid = TemplateLoader(self.opts.templatedir)
            idx_kid.url = self.opts.url
            idx_kid.latest = latest
            idx_kid.groups = self.groups
            outfile = os.path.join(self.outdir, 'index.html')

            tmpl = idx_kid.load(IDXKID)

            stream = tmpl.generate(
                repo_data=repo_data,
                url=self.opts.url,
                groups=self.groups,
                latest=latest,
            )
            with open(outfile, "w", encoding="utf-8") as handle:
                handle.write(stream.render('xhtml', doctype='xhtml-strict'))
            self.say('done\n')

            # rss feed
            if self.opts.url:
                self.do_rss(repo_data, latest)

        # Phase 5: Delete orphaned files and persist state so the next run can stay incremental.
        self.remove_stale()
        self._ensure_connection(self.sconn, 'state').commit()

    def _ensure_connection(
        self, conn: Optional[sqlite.Connection], label: str
    ) -> sqlite.Connection:
        """
        Raise a helpful error if a SQLite connection has not been initialized yet.
        """
        if conn is None:
            msg = f'{label} database connection is not initialized.'
            raise RuntimeError(msg)
        return conn

    def _cursor(self, conn: Optional[sqlite.Connection], label: str) -> sqlite.Cursor:
        """
        Convenience helper for retrieving a cursor from a (possibly optional) connection.
        """
        return self._ensure_connection(conn, label).cursor()

    def setup_state_db(self):
        """
        Initializes the SQLite database used for incremental build state tracking.
        
        The database stores checksums of previously generated files to avoid 
        unnecessary writes. If a specific state directory is not provided, 
        it creates 'state.sqlite' in the output directory.

        @rtype: void
        """
        self.say('Examining state db...')
        if self.opts.statedir:
            # we'll use the md5sum of the repo location to make it unique
            # among multiple repositories sharing the same statedir.
            unique = f"{hashlib.md5(self.outdir.encode()).hexdigest()}.state.sqlite"
            statedb = os.path.join(self.opts.statedir, unique)
        else:
            statedb = os.path.join(self.outdir, 'state.sqlite')

        if os.access(statedb, os.W_OK):
            if self.opts.force:
                # clean slate -- remove state db and start over
                os.unlink(statedb)
        else:
            # state_db not found, go into force mode
            self.opts.force = True

        self.sconn = sqlite.connect(statedb)
        scursor = self._cursor(self.sconn, 'state')

        scursor.execute(
            """CREATE TABLE IF NOT EXISTS state (
                          filename TEXT UNIQUE,
                          checksum TEXT)"""
        )

        # read all state data into memory to track orphaned files
        scursor.execute("SELECT filename, checksum FROM state")
        while True:
            row = scursor.fetchone()
            if row is None:
                break
            self.state_data[row[0]] = row[1]
        self.say('done\n')

    def setup_repo(self):
        """
        Validates the repository structure and initializes database connections.
        
        It parses 'repodata/repomd.xml' to locate the 'primary' (packages) and 
        'other' (changelogs) SQLite databases, as well as the 'group' (comps) file.
        It also checks for schema version compatibility.

        @rtype: void
        """
        self.say('Examining repository...')
        repomd = os.path.join(self.opts.repodir, 'repodata', 'repomd.xml')

        if not os.access(repomd, os.R_OK):
            sys.stderr.write(f'Not found: {repomd}\n')
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)

        with open(repomd, encoding='utf-8') as repomd_fp:
            repoxml = repomd_fp.read()

        xml = fromstring(repoxml) #IGNORE:E1101
        # look for primary_db, other_db, and optionally group

        primary = other = comps = dbversion = None

        xmlns = 'http://linux.duke.edu/metadata/repo'
        for datanode in xml.findall('{%s}data' % xmlns):
            location_node = datanode.find('{%s}location' % xmlns)
            if location_node is None:
                continue
            href = location_node.attrib.get('href')
            if href is None:
                continue
            dtype = datanode.attrib.get('type')
            if dtype == 'primary_db':
                primary = os.path.join(self.opts.repodir, href)
                version_node = datanode.find('{%s}database_version' % xmlns)
                if version_node is not None and version_node.text is not None:
                    dbversion = version_node.text
            elif datanode.attrib['type'] == 'other_db':
                other = os.path.join(self.opts.repodir, href)
            elif datanode.attrib['type'] == 'group':
                comps = os.path.join(self.opts.repodir, href)

        if primary is None or dbversion is None:
            self.say('Sorry, sqlite files not found in the repository.\n'
                     'Please rerun createrepo with a -d flag and try again.\n')
            sys.exit(1)

        if int(dbversion) > SUPPORTED_DB_VERSION:
            self.say(f'Sorry, the db_version in the repository is {dbversion}, but '
                     f'repoview only supports versions up to {SUPPORTED_DB_VERSION}. '
                     'Please check for a newer repoview version.\n')
            sys.exit(1)

        self.say('done\n')

        self.say('Opening primary database...')
        primary = self.z_handler(primary)
        self.pconn = sqlite.connect(primary)
        self.say('done\n')

        self.say('Opening changelogs database...')
        other = self.z_handler(other)
        self.oconn = sqlite.connect(other)
        self.say('done\n')

        if self.opts.comps:
            comps = self.opts.comps

        if comps:
            self.setup_comps_groups(comps)

    def say(self, text):
        """
        Unless in quiet mode, output the text passed.

        @param text: something to say
        @type  text: str

        @rtype: void
        """
        if not self.opts.quiet:
            sys.stdout.write(text)

    def setup_excludes(self):
        """
        Constructs the 'self.exclude' SQL clause to filter packages based on 
        command-line ignore patterns and architecture exclusions.

        @rtype: void
        """
        # Formulate exclusion rule
        xarches = []
        for xarch in self.opts.xarch:
            safe_xarch = xarch.replace("'", "''")
            xarches.append(f"arch != '{safe_xarch}'")
        if xarches:
            self.exclude += ' AND ' + ' AND '.join(xarches)

        pkgs = []
        for pkg in self.opts.ignore:
            safe_pkg = pkg.replace("'", "''").replace("*", "%")
            pkgs.append(f"name NOT LIKE '{safe_pkg}'")
        if pkgs:
            self.exclude += ' AND ' + ' AND '.join(pkgs)

    def setup_outdir(self):
        """
        Prepares the output directory for generating the static site.
        
        It handles cleaning up if force mode is active, ensures correct permissions (755),
        and copies static layout assets (CSS, images) from the template directory.

        @rtype: void
        """
        # Remove the directory if 'force' option is active
        if self.opts.force and os.path.exists(self.outdir):
            shutil.rmtree(self.outdir)

        # Create the output directory and ensure 755 permissions
        os.makedirs(self.outdir, exist_ok=True)
        os.chmod(self.outdir, 0o755)

        # Copy the layout from template if it exists and destination does not exist
        layoutsrc = os.path.join(self.opts.templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc) and not os.path.exists(layoutdst):
            self.say('Copying layout...')
            shutil.copytree(layoutsrc, layoutdst)
            self.say('done\n')

    def get_package_data(self, pkgname):
        """
        Queries the packages and changelog databases to construct a detailed package record.
        
        It aggregates all available versions/architectures of the package into a single
        dictionary structure.

        Returns a dictionary with the following structure:
        pkg_data = {
                    'name':          str,
                    'filename':      str,
                    'summary':       str,
                    'description':   str,
                    'url':           str,
                    'rpm_license':   str,
                    'rpm_sourcerpm': str,
                    'vendor':        str,
                    'rpms':          [] # List of version tuples
                    }

        The "rpms" key list contains tuples:
            (epoch, version, release, arch, time_build, size, location_href,
             author, changelog, time_added)

        @param pkgname: the name of the package to look up
        @type  pkgname: str

        @return: A dictionary containing the package details and version history.
        @rtype:  dict
        """
        # fetch versions
        query = (
            "SELECT pkgKey, epoch, version, release, arch, summary, "
            "description, url, time_build, rpm_license, rpm_sourcerpm, "
            "size_package, location_href, rpm_vendor "
            "FROM packages WHERE name=? AND "
            f"{self.exclude} ORDER BY arch ASC"
        )
        pcursor = self._cursor(self.pconn, 'primary')
        pcursor.execute(query, (pkgname,))

        rows = pcursor.fetchall()

        if not rows:
            # Sorry, nothing found
            return None

        if len(rows) == 1:
            # only one package matching this name
            versions = [rows[0]]
        else:
            # we will use the latest package as the "master" to
            # obtain things like summary, description, etc.
            # go through all available packages and create a dict
            # keyed by (e,v,r)
            temp = {}
            for row in rows:
                temp[(row[1], row[2], row[3], row[4])] = row

            keys = list(temp.keys())
            # Use cmp_to_key to adapt _compare_evra
            keys.sort(key=functools.cmp_to_key(_compare_evra), reverse=True)
            versions = [temp[key] for key in keys]

        pkg_filename = _mkid(PKGFILE % pkgname)

        pkg_data = {
                    'name':          pkgname,
                    'filename':      pkg_filename,
                    'summary':       None,
                    'description':   None,
                    'url':           None,
                    'rpm_license':   None,
                    'rpm_sourcerpm': None,
                    'vendor':        None,
                    'rpms':          []
                    }

        # Build a human-readable payload for the template system.  The first row
        # encountered becomes the canonical metadata, while every row contributes
        # an RPM tuple (epoch, version, release, arch, etc.) for the download table.
        for row in versions:
            (pkg_key, epoch, version, release, arch, summary,
             description, url, time_build, rpm_license, rpm_sourcerpm,
             size_package, location_href, vendor) = row
            if pkg_data['summary'] is None:
                pkg_data['summary'] = summary
                pkg_data['description'] = description
                pkg_data['url'] = url
                pkg_data['rpm_license'] = rpm_license
                pkg_data['rpm_sourcerpm'] = rpm_sourcerpm
                pkg_data['vendor'] = vendor

            size = _humansize(size_package)

            # Get latest changelog entry for each version
            query = (
                "SELECT author, date, changelog "
                "FROM changelog WHERE pkgKey=? "
                "ORDER BY date DESC LIMIT 1"
            )
            ocursor = self._cursor(self.oconn, 'other')
            ocursor.execute(query, (pkg_key,))
            orow = ocursor.fetchone()
            if not orow:
                author = time_added = changelog = None
            else:
                (author, time_added, changelog) = orow
                # strip email and everything that follows from author
                try:
                    author = author[:author.index('<')].strip()
                except ValueError:
                    pass

            pkg_data['rpms'].append((epoch, version, release, arch,
                                     time_build, size, location_href,
                                     author, changelog, time_added))
        return pkg_data


    def do_packages(self, repo_data, group_data, pkgnames):
        """
        Iterate through package names and write the ones that changed.

        @param  repo_data: the dict with repository data
        @type   repo_data: dict
        @param group_data: the dict with group data
        @type  group_data: dict
        @param   pkgnames: a list of package names (strings)
        @type    pkgnames: list

        @return: a list of tuples related to packages, which we later use
                 to create the group page. The members are as such:
                 (pkg_name, pkg_filename, pkg_summary)
        @rtype:  list
        """
        # Each group page needs a compact listing with (name, filename, summary).
        # pkg_tuples doubles as that listing and as an in-memory cache so we do
        # not re-render the same package when it appears in multiple groups.
        pkg_tuples = []

        for pkgname in pkgnames:
            pkg_filename = _mkid(PKGFILE % pkgname)

            if pkgname in self.written:
                pkg_tuples.append(self.written[pkgname])
                continue

            pkg_data = self.get_package_data(pkgname)

            if pkg_data is None:
                # sometimes comps does not reflect reality
                continue

            pkg_tuple = (pkgname, pkg_filename, pkg_data['summary'])
            pkg_tuples.append(pkg_tuple)

            checksum = self.mk_checksum(repo_data, group_data, pkg_data)
            if self.has_changed(pkg_filename, checksum):
                self.say(f'Writing package {pkg_filename}\n')
                self.pkg_kid.group_data = group_data
                self.pkg_kid.pkg_data = pkg_data
                outfile = os.path.join(self.outdir, pkg_filename)
                self.pkg_kid = TemplateLoader(self.opts.templatedir)

                tmpl = self.pkg_kid.load(PKGKID)

                stream = tmpl.generate(
                    group_data=group_data,
                    pkg_data=pkg_data,
                    repo_data=repo_data,
                )
                with open(outfile, "w", encoding="utf-8") as handle:
                    handle.write(stream.render('xhtml', doctype='xhtml-strict'))
                self.written[pkgname] = pkg_tuple
            else:
                self.written[pkgname] = pkg_tuple

        return pkg_tuples

    def mk_checksum(self, *args):
        """
        Calculates a deterministic MD5 checksum for the provided data dictionaries.
        
        This checksum is used for state tracking to detect if the content of a page
        would change based on the data. It sorts dictionary keys to ensure consistency
        before hashing.

        @param *args: One or more dictionaries containing data to be hashed.
        
        @return: An MD5 checksum string of the serialized data.
        @rtype:  str
        """
        mangle = []
        for data in args:
            # since dicts are non-deterministic, we get keys, then sort them,
            # and then create a list of values, which we then pickle.
            keys = list(data.keys())
            keys.sort()

            for key in keys:
                mangle.append(data[key])
        return hashlib.md5((str(mangle)).encode()).hexdigest()

    def has_changed(self, filename, checksum):
        """
        Figure out if the contents of the filename have changed, and do the
        necessary state database tracking bits.

        @param filename: the filename to check if it's changed
        @type  filename: str
        @param checksum: the checksum from the current contents
        @type  checksum: str

        @return: true or false depending on whether the contents are different
        @rtype:  bool
        """
        # calculate checksum
        scursor = self._cursor(self.sconn, 'state')
        if filename not in self.state_data:
            # totally new entry
            query = '''INSERT INTO state (filename, checksum)
                                  VALUES (?, ?)'''
            scursor.execute(query, (filename, checksum))
            return True
        if self.state_data[filename] != checksum:
            # old entry, but changed
            query = """UPDATE state
                          SET checksum=?
                        WHERE filename=?"""
            scursor.execute(query, (checksum, filename))

            # remove it from state_data tracking, so we know we've seen it
            del self.state_data[filename]
            return True
        # old entry, unchanged
        del self.state_data[filename]
        return False

    def remove_stale(self):
        """
        Remove errant stale files from the output directory, left from previous
        repoview runs.

        @rtype void
        """
        scursor = self._cursor(self.sconn, 'state')
        for filename in self.state_data:
            self.say(f'Removing stale file {filename}\n')
            fullpath = os.path.join(self.outdir, filename)
            if os.access(fullpath, os.W_OK):
                os.unlink(fullpath)
            scursor.execute("DELETE FROM state WHERE filename=?", (filename,))

    def z_handler(self, dbfile):
        """
        If the database file is compressed, uncompresses it and returns the
        filename of the uncompressed file.
        
        @param dbfile: the name of the file
        @type  dbfile: str
        
        @return: the name of the uncompressed file
        @rtype:  str
        """
        (_, ext) = os.path.splitext(dbfile)
        opener = {
            '.bz2': BZ2File,
            '.gz': GzipFile,
            '.xz': LZMAFile,
        }.get(ext)
        if opener is None:
            # not compressed (or something odd)
            return dbfile

        fd, unzname = mkstemp('.repoview')
        self.cleanup.append(unzname)

        with opener(dbfile) as zfd, os.fdopen(fd, 'wb') as unzfd:
            while True:
                data = zfd.read(16384)
                if not data:
                    break
                unzfd.write(data)

        return unzname

    def setup_comps_groups(self, compsxml):
        """
        Utility method for parsing comps.xml.

        @param compsxml: the location of comps.xml
        @type  compsxml: str

        @rtype: void
        """
        if libcomps is None:
            raise ImportError('Repoview requires the "libcomps" package to parse comps.xml.')

        self.say('Parsing comps.xml...')
        comps = libcomps.Comps()
        comps.fromxml_f(compsxml)

        for group in comps.groups:
            # if not group.uservisible:
            #     continue
            if not group.packages:
                continue

            group_filename = _mkid(GRPFILE % group.id)
            pkg_names = [pkg.name for pkg in group.packages]
            self.groups.append([group.name, group_filename, group.desc, pkg_names])
        self.say('done\n')

    def setup_rpm_groups(self):
        """
        Fallback method to group packages using their RPM 'Group' tag 
        when a valid comps.xml is not available.

        @rtype: void
        """
        self.say('Collecting group information...')
        query = (
            "SELECT DISTINCT lower(rpm_group) AS rpm_group "
            "FROM packages ORDER BY rpm_group ASC"
        )
        pcursor = self._cursor(self.pconn, 'primary')
        pcursor.execute(query)

        for (rpmgroup,) in pcursor.fetchall():
            pcursor.execute(
                (
                    "SELECT DISTINCT name "
                    "FROM packages "
                    "WHERE lower(rpm_group)=? "
                    f"  AND {self.exclude} "
                    "ORDER BY name"
                ),
                (rpmgroup,),
            )
            pkgnames = [pkgname for (pkgname,) in pcursor.fetchall()]
            group_filename = _mkid(GRPFILE % rpmgroup)
            self.groups.append([rpmgroup, group_filename, None, pkgnames])
        self.say('done\n')

    def get_latest_packages(self, limit=30):
        """
        Return necessary data for the latest NN packages.

        @param limit: how many do you want?
        @type  limit: int

        @return: a list of tuples containting the following data:
                 (pkgname, filename, version, release, built)
        @rtype: list
        """
        self.say('Collecting latest packages...')
        query = (
            "SELECT name "
            "FROM packages "
            f"WHERE {self.exclude} "
            "GROUP BY name "
            f"ORDER BY MAX(time_build) DESC LIMIT {limit}"
        )
        pcursor = self._cursor(self.pconn, 'primary')
        pcursor.execute(query)

        latest = []
        query = (
            "SELECT version, release, time_build "
            "FROM packages "
            "WHERE name = ? "
            "ORDER BY time_build DESC LIMIT 1"
        )
        for (pkgname,) in pcursor.fetchall():
            filename = _mkid(PKGFILE % pkgname.replace("'", "''"))

            pcursor.execute(query, (pkgname,))
            (version, release, built) = pcursor.fetchone()

            latest.append((pkgname, filename, version, release, built))

        self.say('done\n')
        return latest

    def setup_letter_groups(self):
        """
        Figure out which letters we have and set up the necessary groups.

        @return: a string containing all first letters of all packages
        @rtype:  str
        """
        self.say('Collecting letters...')
        query = (
            "SELECT DISTINCT substr(upper(name), 1, 1) AS letter "
            "FROM packages "
            f"WHERE {self.exclude} "
            "ORDER BY letter"
        )
        pcursor = self._cursor(self.pconn, 'primary')
        pcursor.execute(query)

        letters = ''
        for (letter,) in pcursor.fetchall():
            letters += letter
            rpmgroup = f'Letter {letter}'
            description = f'Packages beginning with letter "{letter}".'

            pkgnames = []
            query = (
                "SELECT DISTINCT name "
                "FROM packages "
                "WHERE name LIKE ? "
                f"  AND {self.exclude}"
            )
            pcursor.execute(query, (f'{letter}%',))
            for (pkgname,) in pcursor.fetchall():
                pkgnames.append(pkgname)

            group_filename = _mkid(GRPFILE % rpmgroup).lower()
            letter_group = (rpmgroup, group_filename, description, pkgnames)
            self.letter_groups.append(letter_group)
        self.say('done\n')
        return letters

    def do_rss(self, repo_data, latest):
        """
        Write the RSS feed.

        @param repo_data: the dict containing repository data
        @type  repo_data: dict
        @param latest:    the list of tuples returned by get_latest_packages
        @type  latest:    list

        @rtype: void
        """
        self.say('Generating rss feed...')
        etb = TreeBuilder()
        out = os.path.join(self.outdir, RSSFILE)
        etb.start('rss', {'version': '2.0'})
        etb.start('channel', {})
        self._rss_add_text(etb, 'title', repo_data['title'])
        self._rss_add_text(etb, 'link', f'{self.opts.url}/repoview/{RSSFILE}')
        self._rss_add_text(etb, 'description', f"Latest packages for {repo_data['title']}")
        self._rss_add_text(etb, 'lastBuildDate', time.strftime(ISOFORMAT))
        self._rss_add_text(etb, 'generator', f"Repoview-{repo_data['my_version']}")

        rss_kid = self.pkg_kid.load(RSSKID)
        for row in latest:
            pkg_data = self.get_package_data(row[0])
            if pkg_data is None:
                continue

            self._rss_add_item(etb, rss_kid, repo_data, pkg_data)

        etb.end('channel')
        etb.end('rss')
        rss = etb.close()

        etree = ElementTree(rss)
        out = os.path.join(self.outdir, RSSFILE)
        etree.write(out, 'utf-8')
        self.say('done\n')

    def _rss_add_item(self, builder, rss_kid, repo_data, pkg_data):
        """
        Append a single package entry to the RSS feed builder.
        """
        rpm_entry = pkg_data['rpms'][0]
        epoch, version, release, arch, built = rpm_entry[:5]

        builder.start('item', {})

        pkg_url = f"{self.opts.url}/repoview/{pkg_data['filename']}"
        guid = (
            f"{pkg_url}+{epoch}:{version}-"
            f"{release}.{arch}"
        )
        self._rss_add_text(builder, 'guid', guid)
        self._rss_add_text(builder, 'link', pkg_url)
        pub_date = time.strftime(ISOFORMAT, time.gmtime(int(built)))
        self._rss_add_text(builder, 'pubDate', pub_date)
        title = f"Update: {pkg_data['name']}-{version}-{release}"
        self._rss_add_text(builder, 'title', title)
        description = rss_kid.generate(
            pkg_data=pkg_data, repo_data=repo_data, url=self.opts.url
        ).render()
        self._rss_add_text(builder, 'description', description)

        builder.end('item')

    @staticmethod
    def _rss_add_text(builder, tag, text):
        """Helper for rss field generation."""
        builder.start(tag, {})
        builder.data(text)
        builder.end(tag)


def main():
    """
    Parse the options and invoke the repoview class.

    @rtype: void
    """
    usage = 'usage: %prog [options] repodir'
    parser = OptionParser(usage=usage, version='%prog ' + VERSION)
    parser.add_option('-i', '--ignore-package', dest='ignore', action='append',
        default=[],
        help='Optionally ignore these packages -- can be a shell-style glob. '
        'This is useful for excluding debuginfo packages, e.g.: '
        '"-i *debuginfo* -i *doc*". '
        'The globbing will be done against name-epoch-version-release, '
        'e.g.: "foo-0-1.0-1"')
    parser.add_option('-x', '--exclude-arch', dest='xarch', action='append',
        default=[],
        help='Optionally exclude this arch. E.g.: "-x src -x ia64"')
    parser.add_option('-k', '--template-dir', dest='templatedir',
        default=DEFAULT_TEMPLATEDIR,
        help='Use an alternative directory with kid templates instead of '
        'the default: %default. The template directory must contain four '
        'required template files: index.kid, group.kid, package.kid, rss.kid '
        'and the "layout" dir which will be copied into the repoview directory')
    parser.add_option('-o', '--output-dir', dest='outdir',
        default='repoview',
        help='Create the repoview pages in this subdirectory inside '
        'the repository (default: "%default")')
    parser.add_option('-s', '--state-dir', dest='statedir',
        default=None,
        help='Create the state-tracking db in this directory '
        '(default: store in output directory)')
    parser.add_option('-t', '--title', dest='title',
        default='Repoview',
        help='Describe the repository in a few words. '
        'By default, "%default" is used. '
        'E.g.: -t "Extras for Fedora Core 4 x86"')
    parser.add_option('-u', '--url', dest='url',
        default=None,
        help='Repository URL to use when generating the RSS feed. E.g.: '
        '-u "http://fedoraproject.org/extras/4/i386". Leaving it off will '
        'skip the rss feed generation')
    parser.add_option('-f', '--force', dest='force', action='store_true',
        default=0,
        help='Regenerate the pages even if the repomd checksum has not changed')
    parser.add_option('-q', '--quiet', dest='quiet', action='store_true',
        default=0,
        help='Do not output anything except fatal errors.')
    parser.add_option('-c', '--comps', dest='comps',
        default=None,
        help='Use an alternative comps.xml file (default: off)')
    (opts, args) = parser.parse_args()
    if not args:
        parser.error('Incorrect invocation.')

    opts.repodir = args[0]
    Repoview(opts)

if __name__ == '__main__':
    main()
