#!/usr/bin/python3 -tt
# -*- mode: Python; indent-tabs-mode: nil; -*-
"""
Repoview is a small utility to generate static HTML pages for a repodata
directory, to make it easily browseable.

@author:    Konstantin Ryabitsev & contributors
@copyright: 2005 by Duke University, 2006-2007 by Konstantin Ryabitsev & co
@license:   GPL
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
#pylint: disable-msg=F0401,W0704

__revision__ = '$Id$'

import os
import shutil
import sys
import time
import hashlib as md5

from optparse import OptionParser
from genshi.template      import TemplateLoader

#from rpmUtils.miscutils import compareEVR

try:
    from xml.etree.cElementTree import fromstring, ElementTree, TreeBuilder
except ImportError:
    from cElementTree import fromstring, ElementTree, TreeBuilder

try:
    import sqlite3 as sqlite
except ImportError:
    import sqlite

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

VERSION = '0.6.6'
SUPPORTED_DB_VERSION = 10
DEFAULT_TEMPLATEDIR = '/usr/share/repoview/templates/default'

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

def _humansize(bytes):
    """
    This will return the size in sane units (KiB or MiB).
    
    @param bytes: number of bytes
    @type  bytes: int
    
    @return: human-readable string
    @rtype:  str
    """
    if bytes < 1024:
        return '%d Bytes' % bytes
    bytes = int(bytes)
    kbytes = bytes/1024
    if kbytes/1024 < 1:
        return '%d KiB' % kbytes
    else:
        return '%0.1f MiB' % (float(kbytes)/1024)

def _compare_evra(one, two):
    """
    Just a quickie sorting helper. Yes, I'm avoiding using lambdas.
    
    @param one: tuple of (e,v,r,a)
    @type  one: tuple
    @param two: tuple of (e,v,r,a)
    @type  two: tuple
    
    @return: -1, 0, 1
    @rtype:  int
    """
    return compareEVR(one[:3], two[:3])
    

class Repoview:
    """
    The working horse class.
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
        # list of files to remove at the end of processing
        self.cleanup = []
        self.opts    = opts
        self.outdir  = os.path.join(opts.repodir, 'repoview')
        
        self.exclude    = '1=1'
        self.state_data = {} #?
        self.written    = {} #?
        
        self.groups        = []
        self.letter_groups = []
        
        self.pconn = None # primary.sqlite
        self.oconn = None # other.sqlite
        self.sconn = None # state db
        
        self.setup_repo()
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
        group_kid = TemplateLoader(opts.templatedir)
        group_kid.assume_encoding = "utf-8"
        group_kid.repo_data = repo_data
        self.group_kid = group_kid
        
        pkg_kid = TemplateLoader(opts.templatedir)
        pkg_kid.assume_encoding = "utf-8"
        pkg_kid.repo_data = repo_data
        self.pkg_kid = pkg_kid
        
        count = 0
        for group_data in self.groups + self.letter_groups:
            (grp_name, grp_filename, grp_description, pkgnames) = group_data
            pkgnames.sort()
            
            group_data = {
                          'name':        grp_name,
                          'description': grp_description,
                          'filename':    grp_filename,
                          }
            
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
                self.say('Writing group %s\n' % grp_filename)
                self.group_kid.group_data = group_data
                outfile = os.path.join(self.outdir, grp_filename)
            
                tmpl= self.group_kid.load( GRPKID )

                stream=tmpl.generate(group_data=group_data, repo_data=repo_data)
                with open( outfile, "w" ) as f:
                   f.write( stream.render('xhtml', doctype='xhtml-strict'))
        
        latest = self.get_latest_packages()
        repo_data['latest'] = latest
        repo_data['groups'] = self.groups
        
        checksum = self.mk_checksum(repo_data)
        if self.has_changed('index.html', checksum):
            # Write index.html and rss feed (if asked)
            self.say('Writing index.html...')
            idx_tpt = os.path.join(self.opts.templatedir, IDXKID)
            idx_kid = TemplateLoader(self.opts.templatedir)
            idx_kid.assume_encoding = "utf-8"
            idx_kid.repo_data = repo_data
            idx_kid.url = self.opts.url
            idx_kid.latest = latest
            idx_kid.groups = self.groups
            outfile = os.path.join(self.outdir, 'index.html')
            
            tmpl= idx_kid.load( IDXKID  )

            stream=tmpl.generate( repo_data = repo_data, url=self.opts.url, groups = self.groups, latest = latest )
            with open( outfile, "w" ) as f:
               f.write( stream.render('xhtml', doctype='xhtml-strict'))
            self.say('done\n')
            
            # rss feed
            if self.opts.url:
                self.do_rss(repo_data, latest)
        
        self.remove_stale()
        self.sconn.commit()

    def setup_state_db(self):
        """
        Sets up the state-tracking database.
        
        @rtype: void
        """
        self.say('Examining state db...')
        if self.opts.statedir:
            # we'll use the md5sum of the repo location to make it unique
            unique = '%s.state.sqlite' % md5.md5(self.outdir).hexdigest()
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
        scursor = self.sconn.cursor()

        query = """CREATE TABLE IF NOT EXISTS state (
                          filename TEXT UNIQUE,
                          checksum TEXT)"""
        scursor.execute(query)
        
        # read all state data into memory to track orphaned files
        query = """SELECT filename, checksum FROM state"""
        scursor.execute(query)
        while True:
            row = scursor.fetchone()
            if row is None:
                break
            self.state_data[row[0]] = row[1]        
        self.say('done\n')
        
    def setup_repo(self):
        """
        Examines the repository, makes sure that it's valid and supported,
        and then opens the necessary databases.
        
        @rtype: void
        """
        self.say('Examining repository...')
        repomd = os.path.join(self.opts.repodir, 'repodata', 'repomd.xml')
        
        if not os.access(repomd, os.R_OK):
            sys.stderr.write('Not found: %s\n' % repomd)
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)
        
        repoxml = open(repomd).read()
        
        xml = fromstring(repoxml) #IGNORE:E1101
        # look for primary_db, other_db, and optionally group
        
        primary = other = comps = dbversion = None
        
        xmlns = 'http://linux.duke.edu/metadata/repo'
        for datanode in xml.findall('{%s}data' % xmlns):
            href = datanode.find('{%s}location' % xmlns).attrib['href']
            if datanode.attrib['type'] == 'primary_db':
                primary = os.path.join(self.opts.repodir, href)
                dbversion = datanode.find('{%s}database_version' % xmlns).text
            elif datanode.attrib['type'] == 'other_db':
                other = os.path.join(self.opts.repodir, href)
            elif datanode.attrib['type'] == 'group':
                comps = os.path.join(self.opts.repodir, href)
        
        if primary is None or dbversion is None:
            self.say('Sorry, sqlite files not found in the repository.\n'
                     'Please rerun createrepo with a -d flag and try again.\n')
            sys.exit(1)
        
        if int(dbversion) > SUPPORTED_DB_VERSION:
            self.say('Sorry, the db_version in the repository is %s, but '
                     'repoview only supports versions up to %s. Please check '
                     'for a newer repoview version.\n' % (dbversion, 
                                                          SUPPORTED_DB_VERSION))
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
        Formulates an SQL exclusion rule that we use throughout in order
        to respect the ignores passed on the command line.
        
        @rtype: void
        """
        # Formulate exclusion rule
        xarches = []
        for xarch in self.opts.xarch:
            xarch = xarch.replace("'", "''")
            xarches.append("arch != '%s'" % xarch)
        if xarches:
            self.exclude += ' AND ' + ' AND '.join(xarches)
            
        pkgs = []
        for pkg in self.opts.ignore:
            pkg = pkg.replace("'", "''")
            pkg = pkg.replace("*", "%")
            pkgs.append("name NOT LIKE '%s'" % pkg)
        if pkgs:
            self.exclude += ' AND ' + ' AND '.join(pkgs)

    def setup_outdir(self):
        """
        Sets up the output directory.
        
        @rtype: void
        """
        if self.opts.force and os.access(self.outdir, os.R_OK):
            # clean slate -- remove everything
            shutil.rmtree(self.outdir)
        if not os.access(self.outdir, os.R_OK):
            os.mkdir(self.outdir, 0o755)
            
        layoutsrc = os.path.join(self.opts.templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc) and not os.access(layoutdst, os.R_OK):
            self.say('Copying layout...')
            shutil.copytree(layoutsrc, layoutdst)
            self.say('done\n')
    
    def get_package_data(self, pkgname):
        """
        Queries the packages and changelog databases and returns package data
        in a dict:
        
        pkg_data = {
                    'name':          str,
                    'filename':      str,
                    'summary':       str,
                    'description':   str,
                    'url':           str,
                    'rpm_license':   str,
                    'rpm_sourcerpm': str,
                    'vendor':        str,
                    'rpms':          []
                    }
                    
        the "rpms" key is a list of tuples with the following members:
            (epoch, version, release, arch, time_build, size, location_href,
             author, changelog, time_added)
            
        
        @param pkgname: the name of the package to look up
        @type  pkgname: str
        
        @return: a REALLY hairy dict of values
        @rtype:  list
        """
        # fetch versions
        query = """SELECT pkgKey,
                          epoch,
                          version,
                          release,
                          arch,
                          summary,
                          description,
                          url,
                          time_build,
                          rpm_license,
                          rpm_sourcerpm,
                          size_package,
                          location_href,
                          rpm_vendor
                     FROM packages 
                    WHERE name='%s' AND %s 
                 ORDER BY arch ASC""" % (pkgname, self.exclude)
        pcursor = self.pconn.cursor()
        pcursor.execute(query)
        
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
            
            keys = temp.keys()
            """
            keys.sort(_compare_evra)
            keys.reverse()
            """
            versions = []
            for key in keys:
                versions.append(temp[key])
        
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
            query = '''SELECT author, date, changelog 
                         FROM changelog WHERE pkgKey=%d 
                     ORDER BY date DESC LIMIT 1''' % pkg_key
            ocursor = self.oconn.cursor()
            ocursor.execute(query)
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
        # this is what we return for the group object
        pkg_tuples = []
        
        for pkgname in pkgnames:
            pkg_filename = _mkid(PKGFILE % pkgname)
            
            if pkgname in self.written.keys():
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
                self.say('Writing package %s\n' % pkg_filename)
                self.pkg_kid.group_data = group_data
                self.pkg_kid.pkg_data = pkg_data
                outfile = os.path.join(self.outdir, pkg_filename)
                self.pkg_kid = TemplateLoader(self.opts.templatedir)
            
                tmpl= self.pkg_kid.load( PKGKID )

                stream=tmpl.generate(group_data=group_data, pkg_data=pkg_data, repo_data=repo_data)
                with open( outfile, "w" ) as f:
                   f.write( stream.render('xhtml', doctype='xhtml-strict'))
                self.written[pkgname] = pkg_tuple
            else:
                self.written[pkgname] = pkg_tuple
            
        return pkg_tuples
        
    def mk_checksum(self, *args):
        """
        A fairly dirty function used for state tracking. This is how we know
        if the contents of the page have changed or not.
        
        @param *args: dicts
        @rtype *args: dicts
        
        @return: an md5 checksum of the dicts passed
        @rtype:  str
        """
        mangle = []
        for data in args:
            # since dicts are non-deterministic, we get keys, then sort them,
            # and then create a list of values, which we then pickle.
            keys = data.keys()
            """
            keys.sort()
            """
            
            for key in keys:
                mangle.append(data[key])
        return md5.md5((str(mangle)).encode()).hexdigest()
    
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
        scursor = self.sconn.cursor()
        if filename not in self.state_data.keys():
            # totally new entry
            query = '''INSERT INTO state (filename, checksum)
                                  VALUES ('%s', '%s')''' % (filename, checksum)
            scursor.execute(query)
            return True
        if self.state_data[filename] != checksum:
            # old entry, but changed
            query = """UPDATE state 
                          SET checksum='%s' 
                        WHERE filename='%s'""" % (checksum, filename)
            scursor.execute(query)
            
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
        scursor = self.sconn.cursor()
        for filename in self.state_data.keys():
            self.say('Removing stale file %s\n' % filename)
            fullpath = os.path.join(self.outdir, filename)
            if os.access(fullpath, os.W_OK):
                os.unlink(fullpath)
            query = """DELETE FROM state WHERE filename='%s'""" % filename
            scursor.execute(query)
    
    def z_handler(self, dbfile):
        """
        If the database file is compressed, uncompresses it and returns the
        filename of the uncompressed file.
        
        @param dbfile: the name of the file
        @type  dbfile: str
        
        @return: the name of the uncompressed file
        @rtype:  str
        """
        (junk, ext) = os.path.splitext(dbfile)

        if ext == '.bz2':
            from bz2 import BZ2File
            zfd = BZ2File(dbfile)
        elif ext == '.gz':
            from gzip import GzipFile
            zfd = GzipFile(dbfile)
        elif ext == '.xz':
            from lzma import LZMAFile
            zfd = LZMAFile(dbfile)
        else:
            # not compressed (or something odd)
            return dbfile

        import tempfile
        (unzfd, unzname) = tempfile.mkstemp('.repoview')
        self.cleanup.append(unzname)

        unzfd = open(unzname, 'wb')
        
        while True:
            data = zfd.read(16384)
            if not data: 
                break
            unzfd.write(data)
        zfd.close()
        unzfd.close()
        
        return unzname
    
    def setup_comps_groups(self, compsxml):
        """
        Utility method for parsing comps.xml.
        
        @param compsxml: the location of comps.xml
        @type  compsxml: str
        
        @rtype: void
        """
        from yum.comps import Comps
        
        self.say('Parsing comps.xml...')
        comps = Comps()
        comps.add(compsxml)
        
        for group in comps.groups:
            if not group.user_visible or not group.packages:
                continue
            group_filename = _mkid(GRPFILE % group.groupid)
            self.groups.append([group.name, group_filename, group.description, 
                                group.packages])                
        self.say('done\n')
    
    def setup_rpm_groups(self):
        """
        When comps is not around, we use the (useless) RPM groups.
        
        @rtype: void
        """        
        self.say('Collecting group information...')
        query = """SELECT DISTINCT lower(rpm_group) AS rpm_group 
                     FROM packages 
                 ORDER BY rpm_group ASC"""
        pcursor = self.pconn.cursor()
        pcursor.execute(query)
        
        for (rpmgroup,) in pcursor.fetchall():  
            qgroup = rpmgroup.replace("'", "''")
            query = """SELECT DISTINCT name 
                         FROM packages 
                        WHERE lower(rpm_group)='%s'
                          AND %s
                     ORDER BY name""" % (qgroup, self.exclude)
            pcursor.execute(query)
            pkgnames = []
            for (pkgname,) in pcursor.fetchall():
                pkgnames.append(pkgname)
            
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
        query = """SELECT name
                     FROM packages 
                    WHERE %s
                    GROUP BY name
                 ORDER BY MAX(time_build) DESC LIMIT %s""" % (self.exclude, limit)
        pcursor = self.pconn.cursor()
        pcursor.execute(query)
        
        latest = []
        query = """SELECT version, release, time_build
                     FROM packages
                    WHERE name = '%s'
                    ORDER BY time_build DESC LIMIT 1"""
        for (pkgname,) in pcursor.fetchall():
            filename = _mkid(PKGFILE % pkgname.replace("'", "''"))

            pcursor.execute(query % pkgname)
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
        query = """SELECT DISTINCT substr(upper(name), 1, 1) AS letter 
                     FROM packages 
                    WHERE %s
                 ORDER BY letter""" % self.exclude
        pcursor = self.pconn.cursor()
        pcursor.execute(query)
        
        letters = ''
        for (letter,) in pcursor.fetchall():
            letters += letter
            rpmgroup = 'Letter %s' % letter
            description = 'Packages beginning with letter "%s".' % letter
        
            pkgnames = []
            query = """SELECT DISTINCT name
                         FROM packages
                        WHERE name LIKE '%s%%'
                          AND %s""" % (letter, self.exclude)
            pcursor.execute(query)
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
        etb.start('channel')
        etb.start('title')
        etb.data(repo_data['title'])
        etb.end('title')
        etb.start('link')
        etb.data('%s/repoview/%s' % (self.opts.url, RSSFILE))
        etb.end('link')
        etb.start('description')
        etb.data('Latest packages for %s' % repo_data['title'])
        etb.end('description')
        etb.start('lastBuildDate')
        etb.data(time.strftime(ISOFORMAT))
        etb.end('lastBuildDate')
        etb.start('generator')
        etb.data('Repoview-%s' % repo_data['my_version'])
        etb.end('generator')
        
        rss_tpt = os.path.join(self.opts.templatedir, RSSKID)
        rss_kid = Template(file=rss_tpt)
        rss_kid.assume_encoding = "utf-8"
        rss_kid.repo_data = repo_data
        rss_kid.url = self.opts.url
        
        for row in latest:
            pkg_data = self.get_package_data(row[0])
            
            rpm = pkg_data['rpms'][0]
            (epoch, version, release, arch, built) = rpm[:5]
            etb.start('item')
            etb.start('guid')
            etb.data('%s/repoview/%s+%s:%s-%s.%s' % (self.opts.url, 
                                                     pkg_data['filename'], 
                                                     epoch, version, release, 
                                                     arch))
            etb.end('guid')
            etb.start('link')
            etb.data('%s/repoview/%s' % (self.opts.url, pkg_data['filename']))
            etb.end('link')
            etb.start('pubDate')
            etb.data(time.strftime(ISOFORMAT, time.gmtime(int(built))))
            etb.end('pubDate')
            etb.start('title')
            etb.data('Update: %s-%s-%s' % (pkg_data['name'], version, release))
            etb.end('title')
            rss_kid.pkg_data = pkg_data
            description = rss_kid.serialize()
            etb.start('description')
            etb.data(description.decode('utf-8'))
            etb.end('description')
            etb.end('item')
        
        etb.end('channel')
        etb.end('rss')
        rss = etb.close()
        
        etree = ElementTree(rss)
        out = os.path.join(self.outdir, RSSFILE)
        etree.write(out, 'utf-8')
        self.say('done\n')
        

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
#!/usr/bin/python3 -tt
