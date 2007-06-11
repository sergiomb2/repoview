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

emailre = re.compile('<.*?@.*?>')
def _webify(text):
    """
    Make it difficult to harvest email addresses.
    """
    if text is None: 
        return None
    mo = emailre.search(text)
    if mo:
        email = mo.group(0)
        remail = email.replace('.', '{*}')
        remail = remail.replace('@', '{%}')
        try:
            text = re.sub(email, remail, text)
        except Exception:
            # Sometimes regex fails for unknown reasons.
            pass
    return text

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
    text = text.replace(' ', '')
    return text

class Package:
    """
    A bit of a misnomer -- this is "package" in the sense of repoview, not in 
    the sense of an .rpm file, since it will include multiple architectures.
    """
    def __init__(self, pkgdata):
        (n, e, v, r) = (pkgdata['name'], pkgdata['epoch'], pkgdata['ver'],
                        pkgdata['rel'])
        self.evr = (e, v, r)
        self.n = n
        self.e = e
        self.v = v
        self.r = r
        self.arch = pkgdata['arch']
        self.group = None
        self.rpmgroup = None
        self.summary = None
        self.description = None
        self.url = None
        self.license = None
        self.vendor = None
        self.changelogs = []

        self.summary = pkgdata['summary']
        self.description = pkgdata['description']
        self.url = pkgdata['url']
        self.license = pkgdata['license']
        self.vendor = _webify(pkgdata['vendor'])
        self.rpmgroup = pkgdata['group']

        self.sourcerpm = pkgdata['sourcerpm']
        self.sourceurl = None
        self.sourcename = self._getSourceName()
        if srpmbaseurl and self.sourcename:
            self.sourceurl = os.path.join(srpmbaseurl, 
                'repoview/%s.html' % self.sourcename)
        self.pkgid = pkgdata['pkgId']  # checksum
        
        self.time = int(pkgdata['time_build'])
        self.size = int(pkgdata['size_archive'])
        self.loc = pkgdata['location_href']
        self.packager = _webify(pkgdata['packager'])

    def __str__(self):
        return '%s-%s-%s.%s' % (self.n, self.v, self.r, self.arch)
    
    def __cmp__(self, other):
        """
        Compare a ourselves by NEVR with another package.
        """
        return (cmp(self.n, other.n) or
            compareEVR((self.e, self.v, self.r), (other.e, other.v, other.r)))

    def addChangelogs(self, changelogs):
        """
        Accept changelogs from other-parser and assign them, unless we
        already have some (sometimes happens with multiple architectures).
        """
        if self.changelogs: 
            return 0
        self.changelogs = changelogs
        return 1
    
    def getChangeLogs(self):
        """
        Get the changelogs in the [c-formatted date, author, entry] style.
        """
        retlist = []
        for changelog in self.changelogs:
            author = _webify(changelog['author'])
            date = time.strftime('%c', time.localtime(int(changelog['date'])))
            entry = _webify(changelog['value'])
            retlist.append ([date, author, entry])
        return retlist
        
    def getFileName(self):
        """
        Get the basename of the RPM file in question.
        """
        return os.path.basename(self.loc)

    def getTime(self, format='%c'):
        """
        Return the build time of this package in locale format, unless
        passed as format='strformat'.
        """
        return time.strftime(format, time.localtime(self.time))

    def getSize(self):
        """
        You can access the byte size of the package by looking at arch.size,
        but this will return the size in sane units (KiB or MiB).
        """
        if self.size < 1024:
            return '%d Bytes' % self.size
        kbsize = self.size/1024
        if kbsize/1024 < 1:
            return '%d KiB' % kbsize
        else:
            return '%0.2f MiB' % (float(kbsize)/1024)

    def _getSourceName(self):
        """
        Guess the source name from the srpm name.
        """
        if not self.sourcerpm:
            return None
        i = self.sourcerpm.rfind('-')
        if i > 0:
            i = self.sourcerpm[:i].rfind('-')
            if i > 0:
                return self.sourcerpm[:i]
        return None


class GroupFactory(dict):
    """
    A small utility class that extends the dict functionality to aide in
    kid template generation. It contains the groups, keyed by group id.
    """
    def __init__(self):
        dict.__init__(self)
        self.sortedlist = None
        
    def getSortedList(self, showinvisible=0):
        """
        Get the sorted list of groups. The sorting is done by group id 
        in ascending order (locale-specific).
        """
        if self.sortedlist is None:
            grids = []
            for grid in self.keys():
                if self[grid].uservisible or showinvisible:
                    grids.append(grid)
            grids.sort()
            self.sortedlist = []
            for grid in grids:
                self.sortedlist.append(self[grid])
        return self.sortedlist

class Group:
    """
    Contains a list of packages.
    """
    def __init__(self, grid=None, name=None):
        self.packages = []
        self.grid = grid
        self.name = name
        self.uservisible = True
        self.description = ''

    def __str__(self):
        return self.name

    def add(self, package):
        """
        Add a package name and an exemplary package object to a group.
        The package object can be used to access details other than the
        package name.
        """
        if package not in self.packages:
            self.packages.append(package)

    def getSortedList(self, trim=0, name=None):
        """
        A utility method for calling from kid templates. This will
        return a sorted list of packages, optionally trimmed since
        on large repositories this list can be very large, and makes
        the display useless. If you pass the trim parameter, you must
        pass the nevr parameter, too, so the it knows around which package
        to trim.
        """
        if not self.sorted:
            self.packages.sort()
            self.sorted = True
        if not trim or len(self.packages) <= trim: 
            return self.packages
        i = 0
        for pkg in self.packages:
            if pkg.n == name: 
                break
            i += 1
        half = trim/2
        if i - half < 0:
            return self.packages[0:trim]
        if i + half > len(self.packages):
            return self.packages[-trim:]
        return self.packages[i-half:i+half]        
       
class Repoview:
    """
    The base class.
    """
    def __init__(self, repodir, opts):
        repomd = os.path.join(repodir, 'repodata', 'repomd.xml')
        if not os.access(repomd, os.R_OK):
            sys.stderr.write('Not found: %s\n' % repomd)
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)
        
        self.repodir = repodir
        self.opts    = opts
        
        self.groups = {}
        
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
        # TODO: re-enable
        #self._checkNecessity(checksum)
        
        _say('Opening primary database...', 1)
        primary = self._bzHandler(primary)
        pconn   = sqlite.connect(primary)
        pcursor = pconn.cursor()
        _say('done\n')
        
        _say('Opening changelogs database...', 1)
        other   = self._bzHandler(other)
        oconn   = sqlite.connect(other)
        ocursor = oconn.cursor()
        _say('done\n')
        
        # Formulate exclusion rule
        self.exclude = ''
        xarches = []
        for xarch in opts.xarch:
            xarch = xarch.replace("'", "''")
            xarches.append("arch != '%s'" % xarch)
        if xarches:
            self.exclude += ' AND '.join(xarches)
            
        pkgs = []
        for pkg in opts.ignore:
            pkg = pkg.replace("'", "''")
            pkg = pkg.replace("*", "%")
            pkgs.append("name NOT LIKE '%s'" % pkg)
        if pkgs:
            if self.exclude:
                self.exclude += ' AND '
                self.exclude += ' AND '.join(pkgs)
        
        if not self.exclude:
            # Silly hack to simplify SQL mangling
            self.exclude = '1'
        
        if comps is not None:
            groups = self._getComps(comps)
        else:
            groups = self._getGroups(pcursor)
        
        _say('Collecting letters...', 1)
        
        query = """SELECT DISTINCT substr(upper(name), 0, 1) AS letter 
                     FROM packages 
                    WHERE %s
                 ORDER BY letter""" % self.exclude
        pcursor.execute(query)
        
        letters = []
        for (letter,) in pcursor.fetchall():
            letters.append(letter)
        
        
        ##
        # for each package page, we need the following data:
        # - repository title
        # - group name
        # - surrounding packages
        # - letters
        # - most recent package description and changelogs
        # - list of all packages for this name:
        #   n-e:v-r-a size built
        
        
        for (name, description, packages) in groups:
            print name, description, packages
            sys.exit(0)
            stats = {
                'title': opts.title
                     }
            # fetch 
            query = """SELECT epoch || '.' || version || '.' || release AS ord,
                              arch,
                              epoch,
                              version,
                              release,
                              summary,
                              description,
                              url,
                              time_build,
                              rpm_license,
                              size_package,
                              location_href
                         FROM packages 
                        WHERE name='%s' AND %s 
                     ORDER BY ord, arch ASC""" % (pkgname, self.exclude)
            pcursor.execute(query)
            
            # this is our master package
            row = pcursor.fetchone()
            summary = row[5]
            description = row[6]
            url = row[7]
            rpm_license = row[9]
            rpm_group = pkgmap[pkgname]
            
            print pkgname, rpm_group
            sys.exit(1)
            # HERE #
        sys.exit(0)
        
        # Auxiliary
        self.outdir     = os.path.join(self.repodir, opts.outdir)
        self.arches     = []
        self.packages   = {}
        self.groups     = GroupFactory()
        self.letters    = GroupFactory()
        self.pkgcount   = 0
        self.pkgignored = 0
        
        _say('Reading repository data...', 1)
        self.repodata = RepoMD(None, repomd).repoData
        _say('done\n')
        self._checkNecessity()
        ## Do packages (primary.xml and other.xml)
        self._getPrimary()
        self._getOther()
        self._sortPackages()
        ## Do groups and resolve them
        if self.repodata.has_key('group'):
            self._getGroups()

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
        zfd = BZ2File(dbfile)
        unzfd = open(unzname, 'w')
        
        while True:
            data = zfd.read(8192)
            if not data: break
            unzfd.write(data)
        zfd.close()
        unzfd.close()
        
        return unzname
    
    def _checkNecessity(self, checksum):
        """
        This will look at the checksum for primary.xml and compare it to the
        one recorded during the last run in repoview/checksum. If they match,
        the program exits, unless overridden with -f.
        """
        if self.force: 
            return True
        
        ## Check and get the existing repoview checksum file
        try:
            chkfile = os.path.join(self.homedir, 'checksum')
            fh = open(chkfile, 'r')
            checksum = fh.read()
            fh.close()
        except IOError: 
            return 1
        checksum = checksum.strip()
        if RepoMD.isOld:
            if checksum != self.repodata['primary']['checksum'][1]:
                return 1
        elif checksum != self.repodata['primary'].checksum[1]: 
            return 1
        _say("Repoview: Repository has not changed. Force the run with -f.\n")
        sys.exit(0)

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
    
    def _getGroups(self, cursor, goodnames):
        _say('Collecting group information...', 1)
        groups = []
        query = 'SELECT DISTINCT rpm_group FROM packages ORDER BY rpm_group ASC'
        cursor.execute(query)
        
        pct = 0
        for (rpmgroup,) in cursor.fetchall():  
            pct += 1    
            query = """SELECT name 
                         FROM packages 
                        WHERE rpm_group='%s' 
                     ORDER BY name""" % rpmgroup.replace("'", "''");
            cursor.execute(query)
            packages = []
            for (package,) in cursor.fetchall():
                packages.append(package)
            groups.append([rpmgroup, None, packages])    
            _say('\rCollecting group information: %s groups' % pct)
        _say('...done\n', 1)
        return groups
        
    def _doPackage(self, pkgdata):
        """
        Helper method for cleanliness. Accepts mdparser pkg and sees if we need
        to create a new package or add arches to existing ones, or ignore it
        outright.
        """
        name = pkgdata['name']
        arch = pkgdata['arch']
        if not pkgdata or arch in self.xarch: 
            return False
        if arch not in self.arches: 
            self.arches.append(arch)
        ## We make a package here from pkgdata ##
        if self._checkIgnore(name): 
            return False
        package = Package(pkgdata)
        self.packages.setdefault(name, [])
        self.packages[name].append(package)
        self.csums[package.pkgid] = package
        return True

    def _sortPackages(self):
        """
        Sort packages based on their evr.
        """
        def cmpevr(a, b):
            "Utility function to pass to sort"
            return compareEVR(b.evr, a.evr)
        for name in self.packages:
            self.packages[name].sort(cmpevr)
        
    def _checkIgnore(self, name):
        """
        Check if package name matches the ignore globs passed
        via -i.
        """
        for glob in self.ignore:
            if fnmatch.fnmatchcase(name, glob): 
                return 1
        return 0
        
    def _getPackageByCsum(self, csum):
        """
        Return our representation of a package by the repodata checksum
        provided.
        """
        if self.csums.has_key(csum):
            return self.csums[csum]
        else:
            return None

    def _getOther(self, limit=3):
        """
        Utility method to get data from other.xml.
        """
        _say('parsing other...', 1)
        if RepoMD.isOld:
            loc = self.repodata['other']['relativepath']
        else:
            loc = self.repodata['other'].location[1]
        otherxml = os.path.join(self.repodir, loc)
        ignored = 0
        mdp = MDParser(otherxml)
        for entry in mdp:
            csum = entry['pkgId']
            package = self._getPackageByCsum(csum)
            if package is not None:
                package.addChangelogs(entry['changelog'][:limit])
            else:
                ignored += 1
            _say('\rparsing other: %s packages, %s ignored' % 
                (mdp.count, ignored))
        _say('...done\n', 1)

    def _setGroup(self, package):
        """
        Set the package group membership.
        """
        grid = _mkid(package.rpmgroup)
        if grid not in self.groups.keys():
            group = Group(grid=grid, name=package.rpmgroup)
            self.groups[grid] = group
        else:
            group = self.groups[grid]
        package.group = group
        group.add(package)

    def _makeExtraGroups(self):
        """
        This is a utility method to create the extra groups. Currently,
        the extra groups are:
        __nogroup__: packages not in any other groups
        __latest__: the last NN packages updated
        letter groups: All packages get grouped by their uppercased first 
                       letter
        Any empty groups are then removed.
        """
        nogroup = Group(grid='__nogroup__', 
                        name='Packages not in Groups')
        latest = []
        i = 0
        makerpmgroups = (len(self.groups)<=0)
        for pkglist in self.packages.values():
            for package in pkglist:
                if not package.group and makerpmgroups:
                    self._setGroup(package)
                elif not package.group:
                    package.group = nogroup
                    nogroup.add(package)

                letter = package.n[0].upper()
                if letter not in self.letters.keys():
                    group = Group(grid=letter, name='Letter: %s' % letter)
                    self.letters[letter] = group
                self.letters[letter].add(package)

                # btime is number of seconds since epoch, so reverse logic!
                btime = 0
                if package.time > btime: 
                    btime = package.time
                    if len(latest) < self.maxlatest:
                        latest.append([btime, package])
                    else:
                        latest.sort()
                        latest.reverse()
                        if btime > latest[-1][0]:
                            latest.pop()
                            latest.append([btime, package])
            i += 1
            _say('\rcreating extra groups: %s entries' % i)
        if nogroup.packages:
            self.groups[nogroup.grid] = nogroup
        latest.sort()
        latest.reverse()
        lgroup = Group(grid='__latest__', 
                       name='Last %s Packages Updated' % len(latest))
        for btime, package in latest:
            lgroup.packages.append(package)
        lgroup.sorted = True
        self.groups[lgroup.grid] = lgroup
        _say('...done\n', 1)
        ## Prune empty groups
        for grid in self.groups.keys():
            if not self.groups[grid].packages: 
                del self.groups[grid]

    def _mkOutDir(self, templatedir):
        """
        Create the new repoview directory and copy the layout into it.
        """
        if os.path.isdir(self.outdir):
            _say('deleting garbage dir...', 1)
            shutil.rmtree(self.outdir)
            _say('done\n', 1)
        os.makedirs(self.outdir)
        layoutsrc = os.path.join(templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc):
            _say('copying layout...', 1)
            shutil.copytree(layoutsrc, layoutdst)
            _say('done\n', 1)

    def mkLinkUrl(self, obj, isrss=0):
        """
        This is a utility method passed to kid templates. The templates use 
        it to get the link to a package, group, or layout object without
        having to figure things out on their own.
        """
        if isrss:
            prefix = os.path.join(self.url, 'repoview')
        else:
            prefix = ''
            
        if obj.__class__ is str:
            if isrss:
                ## An RSS page asking for a toplevel link
                link = os.path.join(prefix, rssfile)
                ## A package in parent directory.
            elif obj.endswith('.rpm'):
                link = os.path.join('..', obj)
            else:
                ## A page linking to another page, usually .css
                link = os.path.join(prefix, obj)
        elif obj.__class__ is Package:
            link = os.path.join(prefix, pkgfile % obj.n)
        elif obj.__class__ is Group:
            link = os.path.join(prefix, grfile % obj.grid)
        else:
            ## No idea
            link = '#'
        return link

    def _smartWrite(self, outfile, strdata):
        """
        First check if the strdata changed between versions. Write if yes.
        Move the old file if no.
        """
        oldfile = os.path.join(self.homedir, outfile)
        newfile = os.path.join(self.outdir, outfile)
        if os.path.isfile(oldfile):
            fh = open(oldfile, 'r')
            contents = fh.read()
            fh.close()
            oldcrc = zlib.adler32(contents)
            newcrc = zlib.adler32(strdata)
            if oldcrc == newcrc:
                os.rename(oldfile, newfile)
                return 0
            os.unlink(oldfile)
        fh = open(newfile, 'w')
        fh.write(strdata)
        fh.close()
        return 1        

    def applyTemplates(self, templatedir, title='Repoview', 
                       url='http://localhost'):
        """
        Just what it says. :)
        """
        if not self.packages:
            _say('No packages available.\n')
            sys.exit(0)
        gentime = time.ctime()
        self.url = url
        self._makeExtraGroups()
        self._mkOutDir(templatedir)
        stats = {
            'title': title,
            'pkgcount': self.pkgcount,
            'pkgignored': self.pkgignored,
            'ignorelist': self.ignore,
            'archlist': self.arches,
            'ignorearchlist': self.xarch,
            'VERSION': VERSION,
            'gentime': gentime,
            'dorss': url
            }
        ## Do groups
        grtmpl = os.path.join(templatedir, grkid)
        kobj = Template(file=grtmpl, mkLinkUrl=self.mkLinkUrl,
                letters=self.letters, groups=self.groups, stats=stats)
        w = 0
        p = 0
        for grid in self.groups.keys():            
            kobj.group = self.groups[grid]
            outstr = kobj.serialize(output='xhtml-strict')
            outfile = grfile % grid
            if self._smartWrite(outfile, outstr):
                w += 1
            else:
                p += 1
            _say('writing groups: %s written, %s preserved\r' % (w, p))
        _say('\n', 1)
        ## Do letter groups
        w = 0
        p = 0
        for grid in self.letters.keys():
            kobj.group = self.letters[grid]
            outstr = kobj.serialize(output='xhtml-strict')
            outfile = grfile % grid
            if self._smartWrite(outfile, outstr):
                w += 1
            else:
                p += 1
            _say('writing letter groups: %s written, %s preserved\r' % (w, p))
        _say('\n', 1)
        ## Do packages
        w = 0
        p = 0
        pkgtmpl = os.path.join(templatedir, pkgkid)
        kobj = Template(file=pkgtmpl, mkLinkUrl=self.mkLinkUrl,
                letters=self.letters, stats=stats)
        for pkglist in self.packages.values():
            kobj.pkglist = pkglist
            outstr = kobj.serialize(output='xhtml-strict')
            outfile = pkgfile % pkglist[0].n
            if self._smartWrite(outfile, outstr):
                w += 1
            else:
                p += 1
            _say('writing packages: %s written, %s preserved\r' % (w, p))
        _say('\n', 1)
                
        ## Do index
        _say('generating index...', 1)
        idxtmpl = os.path.join(templatedir, idxkid)
        self.arches.sort()
        kobj = Template(file=idxtmpl, mkLinkUrl=self.mkLinkUrl,
            letters=self.letters, groups=self.groups, stats=stats)
        out = os.path.join(self.outdir, idxfile)
        fh = open(out, 'w')
        kobj.write(out, output='xhtml-strict')
        fh.close()
        out = os.path.join(self.repodir, 'repodata', idxfile)
        shutil.copy(os.path.join(templatedir, redirfile), out)
        _say('done\n')

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
    rv.applyTemplates()

if __name__ == '__main__':
    main()
