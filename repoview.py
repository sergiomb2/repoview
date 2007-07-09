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
#pylint: disable-msg=F0401,C0103

__revision__ = '$Id$'

import os
import re
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
pkgkid    = 'package.kid'
pkgfile   = '%s.html'
grkid     = 'group.kid'
grfile    = '%s.group.html'
idxkid    = 'index.kid'
idxfile   = 'index.html'
redirfile = 'redirect.html'
rsskid    = 'rss.kid'
rssfile   = 'latest-feed.xml'

VERSION = '0.6'
SUPPORTED_DB_VERSION = 10
DEFAULT_TEMPLATEDIR = '/usr/share/repoview/templates'

quiet = 0
def _say(text, flush=0):
    """
    Unless in quiet mode, output the text passed.
    """
    if quiet:
        return
    sys.stdout.write(text)
    if flush: 
        sys.stdout.flush()

def _mkid(text):
    """
    Remove slashes.
    """
    text = text.replace('/', '.')
    text = text.replace(' ', '_').lower()
    return text

def _humanSize(bytes):
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
        return '%0.2f MiB' % (float(kbytes)/1024)
     
class Repoview:
    """
    The base class.
    """
    
    def __del__(self):
        for entry in self.cleanup:
            if os.access(entry, os.W_OK):
                os.unlink(entry)
    
    def __init__(self, repodir, opts):
        # list of files to remove at the end of processing
        self.cleanup = []
        
        repomd = os.path.join(repodir, 'repodata', 'repomd.xml')
        if not os.access(repomd, os.R_OK):
            sys.stderr.write('Not found: %s\n' % repomd)
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)
        
        self.repodir = repodir
        self.opts    = opts
        self.outdir  = os.path.join(repodir, 'repoview')
        
        self.exclude    = '1'
        self.letters    = ''
        self.state_data = {}
        self.written    = {}
        
        self.pcursor = None # primary.sqlite
        self.ocursor = None # other.sqlite
        self.scursor = None # state db
        
        _say('Examining repository...', 1)
        fh = open(repomd)
        repoxml = fh.read()
        fh.close()
        
        xml = fromstring(repoxml) #IGNORE:E1101
        # look for primary_db, other_db, and optionally group
        
        primary = other = comps = checksum = dbversion = None
        
        ns = 'http://linux.duke.edu/metadata/repo'
        for datanode in xml.findall('{%s}data' % ns):
            href = datanode.find('{%s}location' % ns).attrib['href']
            if datanode.attrib['type'] == 'primary_db':
                primary = os.path.join(repodir, href)
                checksum = datanode.find('{%s}checksum' % ns).text
                dbversion = datanode.find('{%s}database_version' % ns).text
            elif datanode.attrib['type'] == 'other_db':
                other = os.path.join(repodir, href)
            elif datanode.attrib['type'] == 'group':
                comps = os.path.join(repodir, href)
        
        if primary is None or dbversion is None:
            _say('Sorry, sqlite files not found in the repository. Please '
                 'rerun createrepo with a -d flag and try again.')
            sys.exit(1)
        
        if int(dbversion) > SUPPORTED_DB_VERSION:
            _say('Sorry, the db_version in the repository is %s, but repoview '
                 'only supports versions up to %s. Please check for a newer '
                 'repoview version.' % (dbversion, SUPPORTED_DB_VERSION))
            sys.exit(1)
        
        _say('done\n')
                
        self._setupOutdir()
        
        # state db can be anywhere, so we'll use the md5sum of the repo
        # location to make them unique
        _say('Examining state db...')
        if opts.statedir:
            unique = '%s.state.sqlite' % md5.md5(self.repodir).hexdigest()
            statedb = os.path.join(opts.statedir, unique)
        else:
            statedb = os.path.join(self.outdir, 'state.sqlite')
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
        
        if opts.force:
            query = 'DELETE FROM state'
            self.scursor.execute(query)
        
        # read all state data into memory to track orphaned files
        query = """SELECT filename, checksum FROM state"""
        self.scursor.execute(query)
        while True:
            row = self.scursor.fetchone()
            if row is None:
                break
            self.state_data[row[0]] = row[1]        
        _say('done\n')
        
        _say('Opening primary database...', 1)
        primary = self._bzHandler(primary)
        pconn = sqlite.connect(primary)
        self.pcursor = pconn.cursor()
        _say('done\n')
        
        _say('Opening changelogs database...', 1)
        other = self._bzHandler(other)
        oconn = sqlite.connect(other)
        self.ocursor = oconn.cursor()
        _say('done\n')
        
        self._setupExcludes()
        
        if comps is not None:
            groups = self._getComps(comps)
        else:
            groups = self._getGroups()
        
        groups += self._getLetterGroups()
        
        repo_data = {
                     'title':      opts.title,
                     'letters':    self.letters,
                     'my_version': VERSION
                    }
        
        group_tpt = os.path.join(opts.templatedir, grkid)
        group_kid = Template(file=group_tpt)
        group_kid.repo_data = repo_data
        self.group_kid = group_kid
        
        pkg_tpt = os.path.join(opts.templatedir, pkgkid)
        pkg_kid = Template(file=pkg_tpt)
        pkg_kid.repo_data = repo_data
        self.pkg_kid = pkg_kid
        
        for (group_name, group_description, pkgnames) in groups:
            pkgnames.sort()
            
            # See if we need to redo this group
            group_filename = _mkid(grfile % group_name)
            
            group_data = {
                          'name':        group_name,
                          'description': group_description,
                          'filename':    group_filename,
                          }
            
            packages = self._doPackages(repo_data, group_data, pkgnames)
            group_data['packages'] = packages
            
            checksum = self._mkChecksum(repo_data, group_data)
            if self._hasChanged(group_filename, checksum):
                # write group file
                _say('Writing group %s\n' % group_filename, 1)        
                self.group_kid.group_data = group_data
                outfile = os.path.join(self.outdir, group_filename)
                self.group_kid.write(outfile, output='xhtml-strict')
        
        self._removeStale()
        sconn.commit()
        sys.exit(0)
    
    def _setupExcludes(self):
        # Formulate exclusion rule
        xarches = []
        for xarch in self.opts.xarch:
            xarch = xarch.replace("'", "''")
            xarches.append("arch != '%s'" % xarch)
        if xarches:
            if self.exclude:
                self.exclude += ' AND '
                self.exclude += ' AND '.join(xarches)
            
        pkgs = []
        for pkg in self.opts.ignore:
            pkg = pkg.replace("'", "''")
            pkg = pkg.replace("*", "%")
            pkgs.append("name NOT LIKE '%s'" % pkg)
        if pkgs:
            if self.exclude:
                self.exclude += ' AND '
                self.exclude += ' AND '.join(pkgs)

    def _setupOutdir(self):        
        if not os.access(self.outdir, os.R_OK):
            os.mkdir(self.outdir, 0755)
            
        layoutsrc = os.path.join(self.opts.templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc) and not os.access(layoutdst, os.R_OK):
            _say('copying layout...', 1)
            shutil.copytree(layoutsrc, layoutdst)
            _say('done\n', 1)
        
    def _doPackages(self, repo_data, group_data, pkgnames):
        # this is what we return for the group object
        pkg_tuples = []
        
        for pkgname in pkgnames:
            pkg_filename = _mkid(pkgfile % pkgname)
            
            if pkgname in self.written.keys():
                pkg_tuples.append(self.written[pkgname])
                continue
                            
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
                # sometimes comps does not reflect reality
                continue
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
                keys.sort(self._compareEVRA)
                keys.reverse()
                versions = []
                for key in keys:
                    versions.append(temp[key])

            
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
                (pkgKey, epoch, version, release, arch, summary,
                 description, url, time_build, rpm_license, size_package,
                 location_href, vendor) = row
                if pkg_data['summary'] is None:
                    pkg_data['summary'] = summary
                    pkg_data['description'] = description
                    pkg_data['url'] = url
                    pkg_data['rpm_license'] = rpm_license
                    pkg_data['vendor'] = vendor
                
                built = time.strftime('%Y-%m-%d', 
                                      time.localtime(int(time_build)))
                size = _humanSize(size_package)
                
                # Get latest changelog entry for each version
                query = '''SELECT author, date, changelog 
                             FROM changelog WHERE pkgKey=%d 
                         ORDER BY date DESC LIMIT 1''' % pkgKey
                self.ocursor.execute(query)
                (author, time_added, changelog) = self.ocursor.fetchone()
                # strip email and everything that follows from author
                try:
                    author = author[:author.index('<')].strip()
                except ValueError:
                    pass
                added = time.strftime('%Y-%m-%d', 
                                      time.localtime(int(time_added)))
                pkg_data['rpms'].append((epoch, version, release, arch,
                                         built, size, location_href,
                                         author, changelog, added))
            
            pkg_tuple = (pkgname, pkg_filename, pkg_data['summary'])
            pkg_tuples.append(pkg_tuple)
            
            checksum = self._mkChecksum(repo_data, group_data, pkg_data)
            if self._hasChanged(pkg_filename, checksum):
                _say('Writing package %s\n' % pkg_filename, 1)
                self.pkg_kid.group_data = group_data
                self.pkg_kid.pkg_data = pkg_data
                outfile = os.path.join(self.outdir, pkg_filename)
                self.pkg_kid.write(outfile, output='xhtml-strict')
                self.written[pkgname] = pkg_tuple
            else:
                self.written[pkgname] = pkg_tuple
        
        return pkg_tuples

    def _compareEVRA(self, one, two):
        return compareEVR(one[:3], two[:3])
            
    def _mkChecksum(self, *args):
        mangle = []
        for data in args:
            # since dicts are non-deterministic, we get keys, then sort them,
            # and then create a list of values, which we then pickle.
            keys = data.keys()
            keys.sort()
            
            for key in keys:
                mangle.append(data[key])
        return md5.md5(str(mangle)).hexdigest()
    
    def _hasChanged(self, filename, checksum):
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
    
    def _removeStale(self):
        for filename in self.state_data.keys():
            _say('Removing stale file %s\n' % filename, 1)
            fullpath = os.path.join(self.outdir, filename)
            if os.access(fullpath, os.W_OK):
                os.unlink(fullpath)
            query = """DELETE FROM state WHERE filename='%s'""" % filename
            self.scursor.execute(query)
    
    def _bzHandler(self, dbfile):
        """
        If the database file is compressed, uncompresses it and returns the
        """
        if dbfile[-4:] != '.bz2':
            # Not compressed
            return dbfile
        
        import tempfile
        from bz2 import BZ2File
        
        (unzfd, unzname) = tempfile.mkstemp()
        self.cleanup.append(unzname)
        
        zfd = BZ2File(dbfile)
        unzfd = open(unzname, 'w')
        
        while True:
            data = zfd.read(8192)
            if not data: break
            unzfd.write(data)
        zfd.close()
        unzfd.close()
        
        return unzname
    
    def _getComps(self, compsxml):
        """
        Utility method for parsing comps.xml.
        [name, description, [packages]]
        """
        from yum.comps import Comps
        
        _say('Parsing comps.xml:', 1)
        groups = []        
        comps = Comps()
        comps.add(compsxml)
        
        pct = 0
        for group in comps.groups:
            if not group.user_visible:
                continue
            pct += 1
            groups.append([group.name, group.description, group.packages])                
            _say('\rParsing comps.xml: %s groups' % pct)
        _say('...done\n', 1)
        return groups
    
    def _getGroups(self):
        _say('Collecting group information...', 1)
        groups = []
        query = 'SELECT DISTINCT rpm_group FROM packages ORDER BY rpm_group ASC'
        self.pcursor.execute(query)
        
        pct = 0
        for (rpmgroup,) in self.pcursor.fetchall():  
            pct += 1    
            query = """SELECT name 
                         FROM packages 
                        WHERE rpm_group='%s' 
                     ORDER BY name""" % rpmgroup.replace("'", "''");
            self.pcursor.execute(query)
            pkgnames = []
            for (pkgname,) in self.pcursor.fetchall():
                pkgnames.append(pkgname)
            groups.append([rpmgroup, None, pkgnames])
            _say('\rCollecting group information: %s groups' % pct)
        _say('...done\n', 1)
        return groups
    
    def _getLetterGroups(self):
        _say('Collecting letters...', 1)
        groups = []
        query = """SELECT DISTINCT substr(upper(name), 0, 1) AS letter 
                     FROM packages 
                    WHERE %s
                 ORDER BY letter""" % self.exclude
        self.pcursor.execute(query)
        
        pct = 0
        for (letter,) in self.pcursor.fetchall():
            pct += 1
            self.letters += letter
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
            groups.append([rpmgroup, description, pkgnames])
            _say('\rCollecting letters: %s letters' % pct)
        _say('...done\n', 1)
        return groups
    
    def _obsolete(self):
        ## Do RSS feed
        if self.url is not None:
            _say('generating rss feed...', 1)
            isoformat = '%a, %d %b %Y %H:%M:%S %z'
            tb = TreeBuilder()
            out = os.path.join(self.outdir, rssfile)
            rss = tb.start('rss', {'version': '2.0'})
            tb.start('channel')
            tb.start('title')
            tb.data(title)
            tb.end('title')
            tb.start('link')
            tb.data('%s/repoview/%s' % (url, rssfile))
            tb.end('link')
            tb.start('description')
            tb.data('Latest packages for %s' % title)
            tb.end('description')
            tb.start('lastBuildDate')
            tb.data(time.strftime(isoformat))
            tb.end('lastBuildDate')
            tb.start('generator')
            tb.data('Repoview-%s' % VERSION)
            tb.end('generator')
            
            rsstmpl = os.path.join(templatedir, rsskid)
            kobj = Template(file=rsstmpl, stats=stats, 
                            mkLinkUrl=self.mkLinkUrl)
            for pkg in self.groups['__latest__'].getSortedList(trim=0):
                tb.start('item')
                tb.start('guid')
                tb.data(self.mkLinkUrl(pkg, isrss=1))
                tb.end('guid')
                tb.start('link')
                tb.data(self.mkLinkUrl(pkg, isrss=1))
                tb.end('link')
                tb.start('pubDate')
                tb.data(pkg.getTime(isoformat))
                tb.end('pubDate')
                tb.start('title')
                tb.data('Update: %s-%s-%s' % (pkg.n, pkg.v, pkg.r))
                tb.end('title')
                tb.start('category')
                tb.data(pkg.n)
                tb.end('category')
                tb.start('category')
                tb.data(pkg.group.name)
                tb.end('category')
                kobj.package = pkg
                description = kobj.serialize()
                tb.start('description')
                tb.data(description)
                tb.end('description')
                tb.end('item')
            tb.end('channel')
            tb.end('rss')
            et = ElementTree(rss)
            et.write(out, 'utf-8')
            _say('done\n')
        
        _say('writing checksum...', 1)
        chkfile = os.path.join(self.outdir, 'checksum')
        fh = open(chkfile, 'w')
        if RepoMD.isOld:
            fh.write(self.repodata['primary']['checksum'][1])
        else:
            fh.write(self.repodata['primary'].checksum[1])
        fh.close()
        _say('done\n')

        _say('Moving new repoview dir in place...', 1)
        # Delete everything except for self.outdir.
        for root, dirs, files in os.walk(self.homedir):
            if self.outdirname in dirs:
                dirs.remove(self.outdirname)
            for d in dirs:
                shutil.rmtree(os.path.join(root, d))
            for f in files:
                os.remove(os.path.join(root, f))
            break
        # Move new files into home.
        for root, dirs, files in os.walk(self.outdir):
            for d in dirs:
                shutil.move(os.path.join(root, d), 
                            os.path.join(self.homedir, d))
            for f in files:
                os.rename(os.path.join(root, f), 
                          os.path.join(self.homedir, f))
            break
        os.rmdir(self.outdir)
        _say('done\n')

def main():
    "Main program code"
    global quiet #IGNORE:W0121
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
            
    quiet = opts.quiet
    repodir = args[0]
    rv = Repoview(repodir, opts)

if __name__ == '__main__':
    main()
