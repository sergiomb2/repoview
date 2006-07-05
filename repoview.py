#!/usr/bin/python -tt
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
# Author: Konstantin Ryabitsev <icon@fedoraproject.org>
#
#pylint: disable-msg=F0401

__revision__ = '$Id$'

import fnmatch
import os
import re
import shutil
import sys
import time
import zlib

from optparse import OptionParser
from elementtree.SimpleXMLWriter import XMLWriter

try:
    from yum.comps import Comps, CompsException
    from yum.mdparser import MDParser
    from repomd.repoMDObject import RepoMD
except ImportError:
    try:
        from noyum.comps import Comps, CompsException
        from noyum.mdparser import MDParser
        from noyum.repoMDObject import RepoMD
    except ImportError:
        print "No yum parsing routines found. Please see README."
        sys.exit(1)

try:
    from rpmUtils.miscutils import compareEVR
except ImportError:
    # No rpmUtils, fall back to simple string based sort
    def compareEVR(x, y): 
        return cmp("%s-%s-%s" % x, "%s-%s-%s" % y)

from kid import Template
##
# Kid generates a FutureWarning on python 2.3
#
if sys.version_info[0] == 2 and sys.version_info[1] == 3:
    import warnings
    warnings.filterwarnings('ignore', category=FutureWarning)

##
# Some hardcoded constants
#
pkgkid = 'package.kid'
pkgfile = '%s.html'
grkid = 'group.kid'
grfile = '%s.group.html'
idxkid = 'index.kid'
idxfile = 'index.html'
rsskid = 'rss.kid'
rssfile = 'latest-feed.xml'

VERSION = '0.5.2'
DEFAULT_TEMPLATEDIR = './templates'

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
        except Exception: #IGNORE:W0703
            ##
            # Sometimes this fails for very odd reasons. Shrug it off.
            #
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

## Jonathan :)
class Archer:
    """
    This class handles all possible architectures for a package, since
    the listing is done by n-e-v-r.html, and a single release can have more
    than one architecture available, e.g. "src". This is effectively where
    all packages end up being: there are no further sublevels.
    """
    def __init__(self, pkgdata):
        self.arch = pkgdata['arch']
        self.time = int(pkgdata['time_build'])
        self.size = int(pkgdata['size_archive'])
        self.loc = pkgdata['location_href']
        self.packager = _webify(pkgdata['packager'])

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
        kbsize = self.size/1024
        if kbsize/1024 < 1:
            return '%d KiB' % kbsize
        else:
            return '%0.2f MiB' % (float(kbsize)/1024)

class Package:
    """
    A bit of a misnomer -- this is "package" in the sense of repoview, not in 
    the sense of an .rpm file, since it will include multiple architectures.
    """
    def __init__(self, n, e, v, r):
        self.nevr = (n, e, v, r)
        self.n = n
        self.e = e
        self.v = v
        self.r = r
        self.group = None
        self.rpmgroup = None
        self.summary = None
        self.description = None
        self.url = None
        self.license = None
        self.vendor = None
        self.arches = {}
        self.incomplete = 1
        self.changelogs = []
        
    def __cmp__(self, other):
        """
        Compare a ourselves by NEVR with another package.
        """
        return (cmp(self.n, other.n) or
            compareEVR((self.e, self.v, self.r), (other.e, other.v, other.r)))

    def doPackage(self, pkgdata):
        """
        Accept a dict with key-value pairs and populate ourselves with it.
        """
        if self.incomplete: 
            self._getPrimary(pkgdata)
        pkgid = pkgdata['pkgId']
        if self.arches.has_key(pkgid): 
            return
        arch = Archer(pkgdata)
        self.arches[pkgid] = arch

    def addChangelogs(self, changelogs):
        """
        Accept changelogs from other-parser and assign them, unless we
        already have some (sometimes happens with multiple architectures).
        """
        if self.changelogs: 
            return 0
        self.changelogs = changelogs
        return 1
    
    def _getPrimary(self, pkgdata):
        """
        A helper method to grab values from pkgdata dict.
        """
        self.summary = pkgdata['summary']
        self.description = pkgdata['description']
        self.url = pkgdata['url']
        self.license = pkgdata['license']
        self.vendor = _webify(pkgdata['vendor'])
        self.rpmgroup = pkgdata['group']
        self.incomplete = 0

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
        
    def getTime(self, format='%c'):
        """
        Convenience method for templates. Returns the latest buildtime from
        all available arches, formatted as requested.
        """
        btime = 0
        for arch in self.arches.values():
            if arch.time > btime:
                btime = arch.time
        date = time.strftime(format, time.localtime(btime))
        return date

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
        self.sorted = 0
        self.uservisible = 1

    def getSortedList(self, trim=0, nevr=None):
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
            self.sorted = 1
        if not trim or len(self.packages) <= trim: 
            return self.packages
        i = 0
        for pkg in self.packages:
            if pkg.nevr == nevr: 
                break
            i += 1
        half = trim/2
        if i - half < 0:
            return self.packages[0:trim]
        if i + half > len(self.packages):
            return self.packages[-trim:]
        return self.packages[i-half:i+half]        
       
class RepoView:
    """
    The base class.
    """
    def __init__(self, repodir, ignore=None, xarch=None, force=0, maxlatest=30):
        self.repodir = repodir
        self.ignore = ignore is not None and ignore or []
        self.xarch = xarch is not None and xarch or []
        self.arches = []
        self.force = force
        self.url = None
        self.olddir = os.path.join(self.repodir, 'repodata', 'repoview')
        self.outdir = os.path.join(self.repodir, 'repodata', '.repoview.new')
        self.packages = {}
        self.csums = {}
        self.groups = GroupFactory()
        self.letters = GroupFactory()
        self.maxlatest = maxlatest
        self.pkgcount = 0
        self.pkgignored = 0
        self.repodata = {}
        repomd = os.path.join(self.repodir, 'repodata', 'repomd.xml')
        if not os.access(repomd, os.R_OK):
            sys.stderr.write('Not found: %s\n' % repomd)
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)
        _say('Reading repository data...', 1)
        self.repodata = RepoMD(None, repomd).repoData
        _say('done\n')
        self._checkNecessity()
        ## Do packages (primary.xml and other.xml)
        self._getPrimary()
        self._getOther()
        ## Do groups and resolve them
        if self.repodata.has_key('group'):
            self._getGroups()

    def _checkNecessity(self):
        """
        This will look at the checksum for primary.xml and compare it to the
        one recorded during the last run in repoview/checksum. If they match,
        the program exits, unless overridden with -f.
        """
        if self.force: 
            return 1
        ## Check and get the existing repoview checksum file
        try:
            chkfile = os.path.join(self.olddir, 'checksum')
            fh = open(chkfile, 'r')
            checksum = fh.read()
            fh.close()
        except IOError: 
            return 1
        checksum = checksum.strip()
        if checksum != self.repodata['primary']['checksum'][1]: 
            return 1
        _say("RepoView: Repository has not changed. Force the run with -f.\n")
        sys.exit(0)

    def _getGroups(self):
        """
        Utility method for parsing comps.xml.
        """
        _say('parsing comps...', 1)
        loc = self.repodata['group']['relativepath']
        comps = Comps()
        try:
            comps.add(os.path.join(self.repodir, loc))
            groups = comps.groups
            comps.isold = 0
        except AttributeError:
            # Must be dealing with yum < 2.5
            try:
                comps.load(os.path.join(self.repodir, loc))
                groups = comps.groups.values()
                comps.isold = 1
            except CompsException:
                print 'Error parsing %s!' % loc
                print 'You may be trying to parse the new comps format'
                print 'with old yum libraries. Falling back to RPM groups.'
                return
        namemap = self._getNameMap()
        pct = 0
        for entry in groups:
            pct += 1
            group = Group()
            if comps.isold:
                group.grid = _mkid(entry.id)
                packages = entry.packages.keys()
            else:
                group.grid = _mkid(entry.groupid)
                packages = entry.packages
            group.name = _webify(entry.name)
            group.description = _webify(entry.description)
            group.uservisible = entry.user_visible
            for pkgname in packages:
                if pkgname in namemap.keys():
                    pkglist = namemap[pkgname]
                    group.packages += pkglist
                    for pkg in pkglist:
                        pkg.group = group
            _say('\rparsing comps: %s groups' % pct)
            self.groups[group.grid] = group
        _say('...done\n', 1)

    def _getNameMap(self):
        """
        Needed for group parsing: since only package names are listed in
        <comps>, this maps names to package objects. The result is in the
        format: {'pkgname': [pkgobject1, pkgobject2, ...]}.
        """
        namemap = {}
        for pkgid in self.packages.keys():
            package = self.packages[pkgid]
            name = package.n
            if name not in namemap.keys(): 
                namemap[name] = [package]
            else:
                namemap[name].append(package)
        return namemap

    def _getPrimary(self):
        """
        Utility method for processing primary.xml.
        """
        _say('parsing primary...', 1)
        loc = self.repodata['primary']['relativepath']
        mdp = MDParser(os.path.join(self.repodir, loc))
        ignored = 0
        for package in mdp:
            if not self._doPackage(package): 
                ignored += 1
            _say('\rparsing primary: %s packages, %s ignored' % (mdp.count,
                ignored))
        self.pkgcount = mdp.count - ignored
        self.pkgignored = ignored
        _say('...done\n', 1)

    def _doPackage(self, pkgdata):
        """
        Helper method for cleanliness. Accepts mdparser pkg and sees if we need
        to create a new package or add arches to existing ones, or ignore it
        outright.
        """
        if not pkgdata or pkgdata['arch'] in self.xarch: 
            return 0
        if pkgdata['arch'] not in self.arches: 
            self.arches.append(pkgdata['arch'])
        ## We make a package here from pkgdata ##
        (n, e, v, r) = (pkgdata['name'], pkgdata['epoch'], 
                        pkgdata['ver'], pkgdata['rel'])
        pkgid = self._mkpkgid(n, e, v, r)
        if self._checkIgnore(pkgid): 
            return 0
        if self.packages.has_key(pkgid):
            package = self.packages[pkgid]
        else:
            package = Package(n, e, v, r)
            package.pkgid = pkgid
            self.packages[pkgid] = package
        package.doPackage(pkgdata)
        self._recordCsums(package)
        return 1
        
    def _checkIgnore(self, pkgid):
        """
        Check if package id (n-e-v-r) matches the ignore globs passed
        via -i.
        """
        for glob in self.ignore:
            if fnmatch.fnmatchcase(pkgid, glob): 
                return 1
        return 0
        
    def _recordCsums(self, package):
        """
        A small helper method to help map repodata package checksums to 
        our representation of packages.
        """
        for csum in package.arches.keys():
            self.csums[csum] = package
    
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
        loc = self.repodata['other']['relativepath']
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
        
    def _mkpkgid(self, n, e, v, r):
        """
        Make the n-e-v-r package id out of n, e, v, r.
        """
        return '%s-%s-%s-%s' % (n, e, v, r)

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
        makerpmgroups = 0
        if not len(self.groups): 
            makerpmgroups = 1
        for pkgid in self.packages.keys():
            package = self.packages[pkgid]
            if package.group is None:
                if makerpmgroups:
                    grid = _mkid(package.rpmgroup)
                    if grid not in self.groups.keys():
                        group = Group(grid=grid, name=package.rpmgroup)
                        self.groups[grid] = group
                    else:
                        group = self.groups[grid]
                    package.group = group
                    group.packages.append(package)
                else:
                    package.group = nogroup
                    nogroup.packages.append(package)
            letter = pkgid[0].upper()
            if letter not in self.letters.keys():
                group = Group(grid=letter, name='Letter: %s' % letter)
                self.letters[letter] = group
            self.letters[letter].packages.append(package)
            # btime is number of seconds since epoch, so reverse logic!
            btime = 0
            for arch in package.arches.values():
                if arch.time > btime: 
                    btime = arch.time
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
        lgroup.sorted = 1
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
            os.removedirs(self.outdir)
            _say('done\n', 1)
        os.mkdir(self.outdir)
        layoutsrc = os.path.join(templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc):
            _say('copying layout...', 1)
            shutil.copytree(layoutsrc, layoutdst)
            _say('done\n', 1)

    def mkLinkUrl(self, obj, isindex=0, isrss=0):
        """
        This is a utility method passed to kid templates. The templates use 
        it to get the link to a package, group, or layout object without
        having to figure things out on their own.
        """
        if isindex and not isrss:
            prefix = 'repoview'
        elif isrss:
            if isindex:
                prefix = os.path.join(self.url, 'repodata')
            else:
                prefix = os.path.join(self.url, 'repodata', 'repoview')
        else:
            prefix = ''
            
        if obj.__class__ is str:
            if not isindex and obj == idxfile:
                ## A page linking up to the index file, which is one dir up
                link = os.path.join('..', obj)
            elif isrss:
                ## An RSS page asking for a toplevel link
                link = os.path.join(prefix, rssfile)
            else:
                ## A page linking to another page, usually .css
                link = os.path.join(prefix, obj)
        elif obj.__class__ is Package:
            link = os.path.join(prefix, pkgfile % obj.pkgid)
        elif obj.__class__ is Group:
            link = os.path.join(prefix, grfile % obj.grid)
        elif obj.__class__ is Archer:
            # loc is taken from the REPOMD files and is relative to
            # the repo directory, so we get out of repodata subdir.
            link = os.path.join('..', '..', obj.loc)
        else:
            ## No idea
            link = '#'
        return link

    def _smartWrite(self, outfile, strdata):
        """
        First check if the strdata changed between versions. Write if yes.
        Move the old file if no.
        """
        oldfile = os.path.join(self.olddir, outfile)
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

    def applyTemplates(self, templatedir, title='RepoView', 
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
            outstr = kobj.serialize()
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
            outstr = kobj.serialize()
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
        for pkgid in self.packages.keys():
            kobj.package = self.packages[pkgid]
            outstr = kobj.serialize()
            outfile = pkgfile % pkgid
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
        out = os.path.join(self.repodir, 'repodata', idxfile)
        fh = open(out, 'w')
        kobj.write(out)
        fh.close()
        _say('done\n')

        ## Do RSS feed
        if self.url is not None:
            _say('generating rss feed...', 1)
            isoformat = '%a, %d %b %Y %H:%M:%S %z'
            out = os.path.join(self.repodir, 'repodata', rssfile)
            w = XMLWriter(out, 'utf-8')
            rss = w.start('rss', version='2.0')
            w.start('channel')
            w.element('title', title)
            w.element('link', '%s/repodata/%s' % (url, rssfile))
            w.element('description', 'Latest packages for %s' % title)
            w.element('lastBuildDate', time.strftime(isoformat))
            w.element('generator', 'Repoview-%s' % VERSION)
            rsstmpl = os.path.join(templatedir, rsskid)
            kobj = Template(file=rsstmpl, stats=stats, 
                            mkLinkUrl=self.mkLinkUrl)
            for pkg in self.groups['__latest__'].getSortedList(trim=0):
                w.start('item')
                w.element('guid', self.mkLinkUrl(pkg, isrss=1))
                w.element('link', self.mkLinkUrl(pkg, isrss=1))
                w.element('pubDate', pkg.getTime(isoformat))
                w.element('title', 'Update: %s-%s-%s' % (pkg.n, pkg.v, pkg.r))
                w.element('category', pkg.n)
                w.element('category', pkg.group.name)
                kobj.package = pkg
                description = kobj.serialize()
                w.element('description', description)
                w.end()
            w.end()
            w.close(rss)
            _say('done\n')
        
        _say('writing checksum...', 1)
        chkfile = os.path.join(self.outdir, 'checksum')
        fh = open(chkfile, 'w')
        fh.write(self.repodata['primary']['checksum'][1])
        fh.close()
        _say('done\n')
        _say('Moving new repoview dir in place...', 1)
        if os.path.isdir(self.olddir):
            os.removedirs(self.olddir)
        os.rename(self.outdir, self.olddir)
        _say('done\n')

def main():
    "Main program code"
    global quiet #IGNORE:W0121
    usage = 'usage: %prog [options] repodir'
    parser = OptionParser(usage=usage, version='%prog ' + VERSION)
    parser.add_option('-i', '--ignore-package', dest='ignore', action='append',
        default=[],
        help='Optionally ignore this package -- can be a shell-style glob. '
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
    parser.add_option('-t', '--title', dest='title', 
        default='RepoView',
        help='Describe the repository in a few words. '
        'By default, "%default" is used. '
        'E.g.: -t "Extras for Fedora Core 4 x86"')
    parser.add_option('-l', '--title-deprecated', dest='dtitle',
        default=None,
        help='This option is deprecated. Please use -t.')
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
    if opts.dtitle is not None:
        opts.title = opts.dtitle
        print 'Option -l is deprecated. Please use -t or --title'
    quiet = opts.quiet
    repodir = args[0]
    rv = RepoView(repodir, ignore=opts.ignore, xarch=opts.xarch, 
                  force=opts.force)
    rv.applyTemplates(opts.templatedir, title=opts.title, url=opts.url)

if __name__ == '__main__':
    main()
