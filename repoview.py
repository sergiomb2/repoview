#!/usr/bin/python -tt
# -*- coding: utf-8 -*-
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
# Author: Konstantin Ryabitsev <icon@duke.edu>
#

import fnmatch
import getopt
import gzip
import os
import re
import shutil
import sys
import time

## 
# Try to import cElementTree, and if that fails attempt to fall back to
# ElementTree, a slower, but pure-python implementation.
#
try: 
    from cElementTree import iterparse
except ImportError: 
    from elementtree.ElementTree import iterparse

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

VERSION = '0.2'
DEFAULT_TEMPLATEDIR = './templates'

def _bn(tag):
    """
    This is a very dirty way to go from {xmlns}tag to just tag.
    """
    try: return tag.split('}')[1]
    except: return tag

emailre = re.compile('<.*?@.*?>')
def _webify(text):
    """
    Make it difficult to harvest email addresses.
    """
    if text is None: return None
    mo = emailre.search(text)
    if mo:
        email = mo.group(0)
        remail = email.replace('.', '{*}')
        remail = remail.replace('@', '{%}')
        text = re.sub(email, remail, text)
    return text

quiet = 0
def _say(text, flush=0):
    """
    Unless in quiet mode, output the text passed.
    """
    if quiet: return
    sys.stdout.write(text)
    if flush: sys.stdout.flush()

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
        self.time = int(pkgdata['time'])
        self.size = int(pkgdata['size'])
        self.loc = pkgdata['location']
        self.packager = pkgdata['packager']

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
        self.arches = {}
        self.incomplete = 1
        self.changelogs = []
        
    def doPackage(self, pkgdata):
        """
        Accept a dict with key-value pairs and populate ourselves with it.
        """
        if self.incomplete: self._getPrimary(pkgdata)
        pkgid = pkgdata['checksum']
        if self.arches.has_key(pkgid): return
        arch = Archer(pkgdata)
        self.arches[pkgid] = arch

    def addChangelogs(self, changelogs):
        """
        Accept changelogs from other-parser and assign them, unless we
        already have some (sometimes happens with multiple architectures).
        """
        if self.changelogs: return 0
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
        self.vendor = pkgdata['vendor']
        self.rpmgroup = pkgdata['group']
        self.incomplete = 0

    def getChangeLogs(self):
        """
        Get the changelogs in the [c-formatted date, author, entry] style.
        """
        self.changelogs.sort()
        self.changelogs.reverse()
        retlist = []
        for changelog in self.changelogs:
            date, author, entry = changelog
            date = time.strftime('%c', time.localtime(date))
            retlist.append ([date, author, entry])
        return retlist

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
            nevrlist = {}
            for package in self.packages:
                nevrlist[package.nevr] = package
            keys = nevrlist.keys()
            keys.sort()
            retlist = []
            for nevr in keys:
                retlist.append(nevrlist[nevr])
            self.packages = retlist
            self.sorted = 1
        if not trim or len(self.packages) <= trim: return self.packages
        retlist = []
        i = 0
        for pkg in self.packages:
            if pkg.nevr == nevr: break
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
    def __init__(self, repodir, ignore=[], xarch=[], force=0, maxlatest=30):
        self.repodir = repodir
        self.ignore = ignore
        self.xarch = xarch
        self.arches = []
        self.force = force
        self.outdir = os.path.join(self.repodir, 'repodata', 'repoview')
        self.packages = {}
        self.groups = GroupFactory()
        self.letters = GroupFactory()
        self.maxlatest = maxlatest
        self.repodata = {}
        repomd = os.path.join(self.repodir, 'repodata', 'repomd.xml')
        if not os.access(repomd, os.R_OK):
            sys.stderr.write('Not found: %s\n' % repomd)
            sys.stderr.write('Does not look like a repository. Exiting.\n')
            sys.exit(1)
        self._parseRepoMD(repomd)
        ## Do packages (primary.xml and other.xml)
        self._parsePrimary()
        self._parseOther()
        ## Do groups and resolve them
        if self.repodata.has_key('group'):
            self._parseGroups()

    def _parseRepoMD(self, loc):
        """
        Parser method for repomd.xml
        """
        type = 'unknown'
        _say('Reading repository data...', 1)
        for event, elem in iterparse(loc, events=('start',)):
            tag = _bn(elem.tag)
            if tag == 'data':
                type = elem.get('type', 'unknown')
                self.repodata[type] = {}
            elif tag == 'location':
                self.repodata[type]['location'] = elem.get('href', '#')
            elif tag == 'checksum':
                self.repodata[type]['checksum'] = elem.text
            elem.clear()
        _say('done\n')
        self._checkNecessity()
            
    def _checkNecessity(self):
        """
        This will look at the checksum for primary.xml and compare it to the
        one recorded during the last run in repoview/checksum. If they match,
        the program exits, unless overridden with -f.
        """
        if self.force: return 1
        ## Check and get the existing repoview checksum file
        try:
            chkfile = os.path.join(self.outdir, 'checksum')
            fh = open(chkfile, 'r')
            checksum = fh.read()
            fh.close()
        except IOError: return 1
        checksum = checksum.strip()
        if checksum != self.repodata['primary']['checksum']: return 1
        _say("RepoView: Repository has not changed. Force the run with -f.\n")
        sys.exit(0)

    def _getFileFh(self, loc):
        """
        Transparently handle gzipped xml files.
        """
        loc = os.path.join(self.repodir, loc)
        if loc[-3:] == '.gz': fh = gzip.open(loc, 'r')
        else: fh = open(loc, 'r')
        return fh

    def _parseGroups(self):
        """
        Utility method for parsing comps.xml.
        """
        _say('parsing comps...', 1)
        fh = self._getFileFh(self.repodata['group']['location'])
        namemap = self._getNameMap()
        pct = 0
        group = Group()
        for event, elem in iterparse(fh):
            tag = elem.tag
            if tag == 'group':
                pct += 1
                _say('\rparsing comps: %s groups' % pct)
                self.groups[group.grid] = group
                group = Group()
            elif tag == 'id':
                group.grid = _mkid(elem.text)
            elif tag == 'name' and not elem.attrib:
                group.name = _webify(elem.text)
            elif tag == 'description' and not elem.attrib:
                group.description = _webify(elem.text)
            elif tag == 'uservisible':
                if elem.text.lower() == 'true': group.uservisible = 1
                else: group.uservisible = 0
            elif tag == 'packagereq':
                pkgname = elem.text
                if pkgname in namemap.keys():
                    pkglist = namemap[pkgname]
                    group.packages += pkglist
                    for pkg in pkglist:
                        pkg.group = group
            elem.clear()
        _say('...done\n', 1)
        fh.close()

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

    def _parsePrimary(self):
        """
        Utility method for parsing primary.xml.
        """
        _say('parsing primary...', 1)
        fh = self._getFileFh(self.repodata['primary']['location'])
        pct = 0
        ignored = 0
        pkgdata = {}
        simpletags = (
            'name', 
            'arch', 
            'summary', 
            'description', 
            'url',
            'packager',
            'checksum',
            'license',
            'group',
            'vendor')
        for event, elem in iterparse(fh):
            tag = _bn(elem.tag)
            if tag == 'package':
                if not self._doPackage(pkgdata): ignored += 1
                pct += 1
                _say('\rparsing primary: %s packages, %s ignored' % 
                        (pct, ignored))
                pkgdata = {}
            elif tag in simpletags:
                pkgdata[tag] = _webify(elem.text)
            elif tag == 'version':
                pkgdata.update(self._getevr(elem))
            elif tag == 'time':
                pkgdata['time'] = elem.get('build', '0')
            elif tag == 'size':
                pkgdata['size'] = elem.get('package', '0')
            elif tag == 'location':
                pkgdata['location'] = elem.get('href', '#')
            elem.clear()
        self.pkgcount = pct - ignored
        self.pkgignored = ignored
        _say('...done\n', 1)
        fh.close()

    def _doPackage(self, pkgdata):
        """
        Helper method for cleanliness. Accepts pkgdata and sees if we need
        to create a new package or add arches to existing ones, or ignore it
        outright.
        """
        if not pkgdata: return 0
        if pkgdata['arch'] in self.xarch: return 0
        if pkgdata['arch'] not in self.arches: 
            self.arches.append(pkgdata['arch'])
        ## We make a package here from pkgdata ##
        (n, e, v, r) = (pkgdata['name'], pkgdata['epoch'], 
                        pkgdata['ver'], pkgdata['rel'])
        pkgid = self._mkpkgid(n, e, v, r)
        if self._checkIgnore(pkgid): return 0
        if self.packages.has_key(pkgid):
            package = self.packages[pkgid]
        else:
            package = Package(n, e, v, r)
            package.pkgid = pkgid
            self.packages[pkgid] = package
        package.doPackage(pkgdata)
        return 1
        
    def _checkIgnore(self, pkgid):
        """
        Check if package id (n-e-v-r) matches the ignore globs passed
        via -i.
        """
        for glob in self.ignore:
            if fnmatch.fnmatchcase(pkgid, glob): return 1
        return 0

    def _parseOther(self, limit=3):
        """
        Utility method to parse other.xml.
        """
        _say('parsing other...', 1)
        fh = self._getFileFh(self.repodata['other']['location'])
        pct = 0
        ignored = 0
        changelogs = []
        evr = None
        cct = 0
        for event, elem in iterparse(fh):
            tag = _bn(elem.tag)
            if tag == 'package':
                n = elem.get('name', '__unknown__')
                pkgid = self._mkpkgid(n, evr['epoch'], evr['ver'], evr['rel'])
                if not self._doOther(pkgid, changelogs): ignored += 1
                pct += 1
                _say('\rparsing other: %s packages, %s ignored' % 
                    (pct, ignored))
                evr = None
                changelogs = []
                n = None
                cct = 0
            elif tag == 'version':
                evr = self._getevr(elem)
            elif tag == 'changelog':
                if cct >= limit: continue
                author = _webify(elem.get('author', 'incognito'))
                date = int(elem.get('date', '0'))
                changelog = _webify(elem.text)
                changelogs.append([date, author, changelog])
                cct += 1
            elem.clear()
        _say('...done\n', 1)
        fh.close()

    def _doOther(self, pkgid, changelogs):
        """
        Helper method for cleanliness.
        """
        if pkgid and changelogs and self.packages.has_key(pkgid):
            package = self.packages[pkgid]
            return package.addChangelogs(changelogs)
        return 0
        
    def _mkpkgid(self, n, e, v, r):
        """
        Make the n-e-v-r package id out of n, e, v, r.
        """
        return '%s-%s-%s-%s' % (n, e, v, r)

    def _getevr(self, elem):
        """
        Utility method to get e-v-r out of the <version> element.
        """
        e = elem.get('epoch', '0')
        v = elem.get('ver', '0')
        r = elem.get('rel', '0')
        return {'epoch': e, 'ver': v, 'rel': r}

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
        latest = {}
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
                if arch.time > btime: btime = arch.time
            if len(latest.keys()) < self.maxlatest:
                latest[btime] = package
            else:
                times = latest.keys()
                times.sort()
                times.reverse()
                oldest = times[-1]
                if btime > oldest:
                    del latest[oldest]
                    latest[btime] = package
            i += 1
            _say('\rcreating extra groups: %s entries' % i)
        if nogroup.packages:
            self.groups[nogroup.grid] = nogroup
        times = latest.keys()
        times.sort()
        times.reverse()
        lgroup = Group(grid='__latest__', 
                       name='Last %s Packages Updated' % len(times))
        for time in times:
            lgroup.packages.append(latest[time])
        lgroup.sorted = 1
        self.groups[lgroup.grid] = lgroup
        _say('...done\n', 1)
        ## Prune empty groups
        for grid in self.groups.keys():
            if not self.groups[grid].packages: del self.groups[grid]

    def _mkOutDir(self, templatedir):
        """
        Remove the existing repoview directory if it exists, and create a
        new one, copying in the layout dir from templates (if found).
        """
        if os.path.isdir(self.outdir):
            _say('deleting old repoview...', 1)
            shutil.rmtree(self.outdir)
            _say('done\n', 1)
        os.mkdir(self.outdir)
        layoutsrc = os.path.join(templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc):
            _say('copying layout...', 1)
            shutil.copytree(layoutsrc, layoutdst)
            _say('done\n', 1)

    def mkLinkUrl(self, object, isindex=0):
        """
        This is a utility method passed to kid templates. The templates use 
        it to get the link to a package, group, or layout object without
        having to figure things out on their own.
        """
        link = '#'
        prefix = ''
        if isindex:
            if self.toplevel: prefix = os.path.join('repodata', 'repoview')
            else: prefix = 'repoview'
        if object.__class__ is str:
            if not isindex and object == idxfile:
                if self.toplevel: link = os.path.join('..', '..', object)
                else: link = os.path.join('..', object)
            else:
                link = os.path.join(prefix, object)
        elif object.__class__ is Package:
            link = os.path.join(prefix, pkgfile % object.pkgid)
        elif object.__class__ is Group:
            link = os.path.join(prefix, grfile % object.grid)
        elif object.__class__ is Archer:
            if isindex and self.toplevel:
                link = os.path.join('..', object.loc)
            else:
                link = os.path.join('..', '..', object.loc)
        return link

    def applyTemplates(self, templatedir, toplevel=0):
        """
        Just what it says. :)
        """
        if not self.packages:
            _say('No packages available.')
            sys.exit(0)
        gentime = time.strftime('%c')
        self.toplevel = toplevel
        self._makeExtraGroups()
        self._mkOutDir(templatedir)
        stats = {
            'pkgcount': self.pkgcount,
            'pkgignored': self.pkgignored,
            'ignorelist': self.ignore,
            'archlist': self.arches,
            'ignorearchlist': self.xarch,
            'VERSION': VERSION,
            'gentime': gentime
            }
        ## Do groups
        grtmpl = os.path.join(templatedir, grkid)
        kobj = Template(file=grtmpl, mkLinkUrl=self.mkLinkUrl,
                letters=self.letters, groups=self.groups, stats=stats)
        i = 0
        for grid in self.groups.keys():            
            kobj.group = self.groups[grid]
            out = os.path.join(self.outdir, grfile % grid)
            fh = open(out, 'w')
            kobj.write(fh)
            fh.close()
            i += 1
            _say('writing groups: %s written\r' % i)
        _say('\n', 1)
        ## Do letter groups
        i = 0
        for grid in self.letters.keys():
            kobj.group = self.letters[grid]
            out = os.path.join(self.outdir, grfile % grid)
            fh = open(out, 'w')
            kobj.write(fh)
            fh.close()
            i += 1
            _say('writing letter groups: %s written\r' % i)
        _say('\n', 1)
        ## Do packages
        i = 0
        pkgtmpl = os.path.join(templatedir, pkgkid)
        kobj = Template(file=pkgtmpl, mkLinkUrl=self.mkLinkUrl,
                letters=self.letters, stats=stats)
        for pkgid in self.packages.keys():
            kobj.package = self.packages[pkgid]
            out = os.path.join(self.outdir, pkgfile % pkgid)
            fh = open(out, 'w')
            kobj.write(fh)
            fh.close()
            i += 1
            _say('writing packages: %s written\r' % i)
        _say('\n', 1)
        ## Do index
        _say('generating index...', 1)
        idxtmpl = os.path.join(templatedir, idxkid)
        self.arches.sort()
        kobj = Template(file=idxtmpl, mkLinkUrl=self.mkLinkUrl,
            letters=self.letters, groups=self.groups, stats=stats)
        if self.toplevel: out = os.path.join(self.repodir, idxfile)
        else: out = os.path.join(self.repodir, 'repodata', idxfile)
        fh = open(out, 'w')
        kobj.write(out)
        fh.close()
        _say('done\n')
        _say('writing checksum...', 1)
        chkfile = os.path.join(self.outdir, 'checksum')
        fh = open(chkfile, 'w')
        fh.write(self.repodata['primary']['checksum'])
        fh.close()
        _say('done\n')

def usage(ecode=0):
    print """repoview [-i name] [-x arch] [-k dir] [-t] [-f] [-q] [repodir]
    This will make your repository browseable
    -i name
        Optionally ignore this package -- can be a shell-style glob.
        This is useful for excluding debuginfo packages:
        -i *debuginfo* -i *doc*
        The globbing will be done against name-epoch-version-release, 
        e.g. foo-0-1.0-1
    -x arch
        Optionally exclude this arch. E.g.:
        -x src -x ia64
    -k templatedir
        Use an alternative directory with kid templates instead of
        the default: %s
        The template directory must contain three required template 
        files: index.kid, group.kid, package.kid and the
        "layout" dir which will be copied into the repoview directory.
    -t
        Place the index.html into the top level of the repodir, instead of 
        just in repodata/index.html.
    -f
        Regenerate the pages even if the repomd checksum hasn't changed.
    -q
        Do not output anything except fatal erros.
    repodir
        Where to look for the 'repodata' directory.
    """ % DEFAULT_TEMPLATEDIR
    sys.exit(ecode)

def main(args):
    global quiet
    if not args: usage()
    ignore = []
    xarch = []
    toplevel = 0
    templatedir = DEFAULT_TEMPLATEDIR
    force = 0
    try:
        gopts, cmds = getopt.getopt(args, 'i:x:k:tfqh', ['help'])
        if not cmds: usage(1)
        for o,a in gopts:
            if o == '-i': ignore.append(a)
            elif o == '-x': xarch.append(a)
            elif o == '-k': templatedir = a
            elif o == '-t': toplevel = 1
            elif o == '-f': force = 1
            elif o == '-q': quiet = 1
            else: usage()
        repodir = cmds[0]
    except getopt.error, e:
        print "Error: %s" % e
        usage(1)
    if templatedir is None:
        templatedir = os.path.join(repodir, 'templates')
    rv = RepoView(repodir, ignore=ignore, xarch=xarch, force=force)
    rv.applyTemplates(templatedir, toplevel=toplevel)

if __name__ == '__main__':
    main(sys.argv[1:])
