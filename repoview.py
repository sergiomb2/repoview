#!/usr/bin/python -tt
# -*- mode: Python; indent-tabs-mode: nil; -*-
"""
Repoview is a small utility to generate static HTML pages for a repodata
directory, to make it easily browseable.
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
import md5

from optparse import OptionParser
from kid      import Template

from rpmUtils.miscutils import compareEVR

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

VERSION = '0.6'
SUPPORTED_DB_VERSION = 10
DEFAULT_TEMPLATEDIR = '/usr/share/repoview/templates'

def _mkid(text):
    """
    Remove slashes.
    """
    text = text.replace('/', '.')
    text = text.replace(' ', '_').lower()
    return text

def _humansize(bytes):
    """
    This will return the size in sane units (KiB or MiB).
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
        # list of files to remove at the end of processing
        self.cleanup = []
        self.opts    = opts
        self.outdir  = os.path.join(opts.repodir, 'repoview')
        
        self.exclude    = '1=1'
        self.state_data = {} #?
        self.written    = {} #?
        
        self.groups        = []
        self.letter_groups = []
        
        self.pcursor = None # primary.sqlite
        self.ocursor = None # other.sqlite
        self.scursor = None # state db
        
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
        
        group_kid = Template(file=os.path.join(opts.templatedir, GRPKID))
        group_kid.repo_data = repo_data
        self.group_kid = group_kid
        
        pkg_kid = Template(file=os.path.join(opts.templatedir, PKGKID))
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
                self.group_kid.write(outfile, output='xhtml-strict')
        
        latest = self.get_latest_packages()
        repo_data['latest'] = latest
        repo_data['groups'] = self.groups
        
        checksum = self.mk_checksum(repo_data)
        if self.has_changed('index.html', checksum):
            # Write index.html and rss feed (if asked)
            self.say('Writing index.html...')
            idx_tpt = os.path.join(self.opts.templatedir, IDXKID)
            idx_kid = Template(file=idx_tpt)
            idx_kid.repo_data = repo_data
            idx_kid.url = self.opts.url
            idx_kid.latest = latest
            idx_kid.groups = self.groups
            outfile = os.path.join(self.outdir, 'index.html')
            idx_kid.write(outfile, output='xhtml-strict')
            self.say('done\n')
            
            # rss feed
            if self.opts.url:
                self.do_rss(repo_data, latest)
        
        self.remove_stale()
        self.scursor.connection.commit()

    def setup_state_db(self):
        """
        Sets up the state-tracking database.
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
        
        sconn = sqlite.connect(statedb)
        self.scursor = sconn.cursor()
        
        try:
            query = """CREATE TABLE state (
                              filename TEXT UNIQUE,
                              checksum TEXT)"""
            self.scursor.execute(query)
        except sqlite.OperationalError:
            # naively pretend this only happens when the table already exists
            pass
        
        # read all state data into memory to track orphaned files
        query = """SELECT filename, checksum FROM state"""
        self.scursor.execute(query)
        while True:
            row = self.scursor.fetchone()
            if row is None:
                break
            self.state_data[row[0]] = row[1]        
        self.say('done\n')
        
    def setup_repo(self):
        """
        Examines the repository, makes sure that it's valid and supported,
        and then opens the necessary databases.
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
            self.say('Sorry, sqlite files not found in the repository. Please '
                      'rerun createrepo with a -d flag and try again.')
            sys.exit(1)
        
        if int(dbversion) > SUPPORTED_DB_VERSION:
            self.say('Sorry, the db_version in the repository is %s, but '
                      'repoview only supports versions up to %s. Please check '
                      'for a newer repoview version.' % (dbversion, 
                                                         SUPPORTED_DB_VERSION))
            sys.exit(1)
        
        self.say('done\n')
        
        self.say('Opening primary database...')
        primary = self.bz_handler(primary)
        pconn = sqlite.connect(primary)
        self.pcursor = pconn.cursor()
        self.say('done\n')
        
        self.say('Opening changelogs database...')
        other = self.bz_handler(other)
        oconn = sqlite.connect(other)
        self.ocursor = oconn.cursor()
        self.say('done\n')
        
        if comps:
            self.setup_comps_groups(comps)

    def say(self, text):
        """
        Unless in quiet mode, output the text passed.
        """
        if not self.opts.quiet:
            sys.stdout.write(text)
        
    def setup_excludes(self):
        """
        Formulates an SQL exclusion rule that we use throughout in order
        to respect the ignores passed on the command line.
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
        """
        if self.opts.force:
            # clean slate -- remove everything
            shutil.rmtree(self.outdir)
        if not os.access(self.outdir, os.R_OK):
            os.mkdir(self.outdir, 0755)
            
        layoutsrc = os.path.join(self.opts.templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc) and not os.access(layoutdst, os.R_OK):
            self.say('Copying layout...')
            shutil.copytree(layoutsrc, layoutdst)
            self.say('done\n')
    
    def get_package_data(self, pkgname):
        """
        Queries the packages and changelog databases and returns package data.
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
                          size_package,
                          location_href,
                          rpm_vendor
                     FROM packages 
                    WHERE name='%s' AND %s 
                 ORDER BY arch ASC""" % (pkgname, self.exclude)
        self.pcursor.execute(query)
        
        rows = self.pcursor.fetchall()
        
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
            keys.sort(_compare_evra)
            keys.reverse()
            versions = []
            for key in keys:
                versions.append(temp[key])
        
        pkg_filename = _mkid(PKGFILE % pkgname)
        
        pkg_data = {
                    'name':        pkgname,
                    'filename':    pkg_filename,
                    'summary':     None,
                    'description': None,
                    'url':         None,
                    'rpm_license': None,
                    'vendor':      None,
                    'rpms':        []
                    }
        
        for row in versions:
            (pkg_key, epoch, version, release, arch, summary,
             description, url, time_build, rpm_license, size_package,
             location_href, vendor) = row
            if pkg_data['summary'] is None:
                pkg_data['summary'] = summary
                pkg_data['description'] = description
                pkg_data['url'] = url
                pkg_data['rpm_license'] = rpm_license
                pkg_data['vendor'] = vendor
            
            size = _humansize(size_package)
            
            # Get latest changelog entry for each version
            query = '''SELECT author, date, changelog 
                         FROM changelog WHERE pkgKey=%d 
                     ORDER BY date DESC LIMIT 1''' % pkg_key
            self.ocursor.execute(query)
            (author, time_added, changelog) = self.ocursor.fetchone()
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
                self.pkg_kid.write(outfile, output='xhtml-strict')
                self.written[pkgname] = pkg_tuple
            else:
                self.written[pkgname] = pkg_tuple
            
            
                
        return pkg_tuples
        
    def mk_checksum(self, *args):
        """
        A fairly dirty function used for state tracking. This is how we know
        if the contents of the page have changed or not.
        """
        mangle = []
        for data in args:
            # since dicts are non-deterministic, we get keys, then sort them,
            # and then create a list of values, which we then pickle.
            keys = data.keys()
            keys.sort()
            
            for key in keys:
                mangle.append(data[key])
        return md5.md5(str(mangle)).hexdigest()
    
    def has_changed(self, filename, checksum):
        """
        Figure out if the contents of the filename have changed, and do the
        necessary state database tracking bits.
        """
        # calculate checksum
    
        if filename not in self.state_data.keys():
            # totally new entry
            query = '''INSERT INTO state (filename, checksum)
                                  VALUES ('%s', '%s')''' % (filename, checksum)
            self.scursor.execute(query)
            return True
        if self.state_data[filename] != checksum:
            # old entry, but changed
            query = """UPDATE state 
                          SET checksum='%s' 
                        WHERE filename='%s'""" % (checksum, filename)
            self.scursor.execute(query)
            
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
        """
        for filename in self.state_data.keys():
            self.say('Removing stale file %s\n' % filename)
            fullpath = os.path.join(self.outdir, filename)
            if os.access(fullpath, os.W_OK):
                os.unlink(fullpath)
            query = """DELETE FROM state WHERE filename='%s'""" % filename
            self.scursor.execute(query)
    
    def bz_handler(self, dbfile):
        """
        If the database file is compressed, uncompresses it and returns the
        """
        if dbfile[-4:] != '.bz2':
            # Not compressed
            return dbfile
        
        import tempfile
        from bz2 import BZ2File
        
        (unzfd, unzname) = tempfile.mkstemp('.repoview')
        self.cleanup.append(unzname)
        
        zfd = BZ2File(dbfile)
        unzfd = open(unzname, 'w')
        
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
        """
        from yum.comps import Comps
        
        self.say('Parsing comps.xml...')
        comps = Comps()
        comps.add(compsxml)
        
        for group in comps.groups:
            if not group.user_visible or not group.packages:
                continue
            group_filename = _mkid(GRPFILE % group.name)
            self.groups.append([group.name, group_filename, group.description, 
                                group.packages])                
        self.say('done\n')
    
    def setup_rpm_groups(self):
        """
        When comps is not around, we use the (useless) RPM groups.
        """        
        self.say('Collecting group information...')
        query = 'SELECT DISTINCT rpm_group FROM packages ORDER BY rpm_group ASC'
        self.pcursor.execute(query)
        
        for (rpmgroup,) in self.pcursor.fetchall():  
            qgroup = rpmgroup.replace("'", "''")
            query = """SELECT name 
                         FROM packages 
                        WHERE rpm_group='%s'
                          AND %s
                     ORDER BY name""" % (qgroup, self.exclude)
            self.pcursor.execute(query)
            pkgnames = []
            for (pkgname,) in self.pcursor.fetchall():
                pkgnames.append(pkgname)
            
            group_filename = _mkid(GRPFILE % rpmgroup)
            self.groups.append([rpmgroup, group_filename, None, pkgnames])
        self.say('done\n')
    
    def get_latest_packages(self, limit=30):
        """
        Return necessary data for the latest NN packages.
        """
        self.say('Collecting latest packages...')
        query = """SELECT DISTINCT name, 
                          version,
                          release,
                          time_build 
                     FROM packages 
                    WHERE %s
                 ORDER BY time_build DESC LIMIT %s""" % (self.exclude, limit)
        self.pcursor.execute(query)
        
        latest = []
        for (pkgname, version, release, built) in self.pcursor.fetchall():
            filename = _mkid(PKGFILE % pkgname)
            latest.append((pkgname, filename, version, release, built))
        
        self.say('done\n')
        return latest
        
    def setup_letter_groups(self):
        """
        Figure out which letters we have and set up the necessary groups.
        """
        self.say('Collecting letters...')
        query = """SELECT DISTINCT substr(upper(name), 0, 1) AS letter 
                     FROM packages 
                    WHERE %s
                 ORDER BY letter""" % self.exclude
        self.pcursor.execute(query)
        
        letters = ''
        for (letter,) in self.pcursor.fetchall():
            letters += letter
            rpmgroup = 'Letter %s' % letter
            description = 'Packages beginning with letter "%s".' % letter
        
            pkgnames = []
            query = """SELECT DISTINCT name
                         FROM packages
                        WHERE name LIKE '%s%%'
                          AND %s""" % (letter, self.exclude)
            self.pcursor.execute(query)
            for (pkgname,) in self.pcursor.fetchall():
                pkgnames.append(pkgname)
                
            group_filename = _mkid(GRPFILE % rpmgroup)
            letter_group = (rpmgroup, group_filename, description, pkgnames)
            self.letter_groups.append(letter_group)
        self.say('done\n')
        return letters
    
    def do_rss(self, repo_data, latest):
        """
        Write the RSS feed.
        """
        self.say('Generating rss feed...')
        tb = TreeBuilder()
        out = os.path.join(self.outdir, RSSFILE)
        tb.start('rss', {'version': '2.0'})
        tb.start('channel')
        tb.start('title')
        tb.data(repo_data['title'])
        tb.end('title')
        tb.start('link')
        tb.data('%s/repoview/%s' % (self.opts.url, RSSFILE))
        tb.end('link')
        tb.start('description')
        tb.data('Latest packages for %s' % repo_data['title'])
        tb.end('description')
        tb.start('lastBuildDate')
        tb.data(time.strftime(ISOFORMAT))
        tb.end('lastBuildDate')
        tb.start('generator')
        tb.data('Repoview-%s' % repo_data['my_version'])
        tb.end('generator')
        
        rss_tpt = os.path.join(self.opts.templatedir, RSSKID)
        rss_kid = Template(file=rss_tpt)
        rss_kid.repo_data = repo_data
        rss_kid.url = self.opts.url
        
        for row in latest:
            pkg_data = self.get_package_data(row[0])
            
            rpm = pkg_data['rpms'][0]
            (e, v, r, a, built) = rpm[:5]
            tb.start('item')
            tb.start('guid')
            tb.data('%s/repoview/%s+%s:%s-%s.%s' % (self.opts.url, 
                                                    pkg_data['filename'], 
                                                    e, v, r, a))
            tb.end('guid')
            tb.start('link')
            tb.data('%s/repoview/%s' % (self.opts.url, pkg_data['filename']))
            tb.end('link')
            tb.start('pubDate')
            tb.data(time.strftime(ISOFORMAT, time.localtime(int(built))))
            tb.end('pubDate')
            tb.start('title')
            tb.data('Update: %s-%s-%s' % (pkg_data['name'], v, r))
            tb.end('title')
            rss_kid.pkg_data = pkg_data
            description = rss_kid.serialize()
            tb.start('description')
            tb.data(description)
            tb.end('description')
            tb.end('item')
        
        tb.end('channel')
        tb.end('rss')
        rss = tb.close()
        
        et = ElementTree(rss)
        out = os.path.join(self.outdir, RSSFILE)
        et.write(out, 'utf-8')
        self.say('done\n')
        

def main():
    """
    Parse the options and invoke the repoview class.
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
    (opts, args) = parser.parse_args()
    if not args:
        parser.error('Incorrect invocation.')
            
    opts.repodir = args[0]
    Repoview(opts)

if __name__ == '__main__':
    main()