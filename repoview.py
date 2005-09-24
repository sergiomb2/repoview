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
# Author: Konstantin Ryabitsev <icon@duke.edu>
#

__revision__ = '$Id$'

import fnmatch
import getopt
import os
import re
import shutil
import sys
import time
import zlib

try:
    from yum.comps import Comps
    from yum.mdparser import MDParser
    from repomd.repoMDObject import RepoMD
except ImportError:
    try:
        from noyum.comps import Comps #IGNORE:F0401
        from noyum.mdparser import MDParser #IGNORE:F0401
        from noyum.repoMDObject import RepoMD #IGNORE:F0401
    except ImportError:
        print "No yum parsing routines found. Please see README."
        sys.exit(1)

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

VERSION = '0.4'
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
        self.summary = None
        self.description = None
        self.url = None
        self.license = None
        self.vendor = None
        self.arches = {}
        self.incomplete = 1
        self.changelogs = []
        
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
        if not trim or len(self.packages) <= trim: 
            return self.packages
        retlist = []
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
        self.olddir = os.path.join(self.repodir, 'repodata', 'repoview')
        self.outdir = os.path.join(self.repodir, 'repodata', '.repoview.new')
        self.packages = {}
        self.csums = {}
        self.groups = GroupFactory()
        self.letters = GroupFactory()
        self.maxlatest = maxlatest
        self.toplevel = 0
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
            chkfile = os.path.join(self.outdir, 'checksum')
            fh = open(chkfile, 'r')
            checksum = fh.read()
            fh.close()
        except IOError: return 1
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
        groups = Comps(os.path.join(self.repodir, loc)).groups.values()
        namemap = self._getNameMap()
        pct = 0
        for entry in groups:
            pct += 1
            group = Group()
            group.grid = _mkid(entry.id)
            group.name = _webify(entry.name)
            group.description = _webify(entry.description)
            group.uservisible = entry.user_visible
            for pkgname in entry.packages.keys():
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
            shutil.rmtree(self.outdir)
            _say('done\n', 1)
        os.mkdir(self.outdir)
        layoutsrc = os.path.join(templatedir, 'layout')
        layoutdst = os.path.join(self.outdir, 'layout')
        if os.path.isdir(layoutsrc):
            _say('copying layout...', 1)
            shutil.copytree(layoutsrc, layoutdst)
            _say('done\n', 1)

    def mkLinkUrl(self, obj, isindex=0):
        """
        This is a utility method passed to kid templates. The templates use 
        it to get the link to a package, group, or layout object without
        having to figure things out on their own.
        """
        link = '#'
        prefix = ''
        if isindex:
            if self.toplevel: 
                prefix = os.path.join('repodata', 'repoview')
            else: prefix = 'repoview'
        if obj.__class__ is str:
            if not isindex and obj == idxfile:
                if self.toplevel: 
                    link = os.path.join('..', '..', obj)
                else: link = os.path.join('..', obj)
            else:
                link = os.path.join(prefix, obj)
        elif obj.__class__ is Package:
            link = os.path.join(prefix, pkgfile % obj.pkgid)
        elif obj.__class__ is Group:
            link = os.path.join(prefix, grfile % obj.grid)
        elif obj.__class__ is Archer:
            if isindex and self.toplevel:
                link = os.path.join('..', obj.loc)
            else:
                link = os.path.join('..', '..', obj.loc)
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

    def applyTemplates(self, templatedir, toplevel=0, title='RepoView'):
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
            'title': title,
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
        if self.toplevel: 
            out = os.path.join(self.repodir, idxfile)
        else: 
            out = os.path.join(self.repodir, 'repodata', idxfile)
        fh = open(out, 'w')
        kobj.write(out)
        fh.close()
        _say('done\n')
        _say('writing checksum...', 1)
        chkfile = os.path.join(self.outdir, 'checksum')
        fh = open(chkfile, 'w')
        fh.write(self.repodata['primary']['checksum'][1])
        fh.close()
        _say('done\n')
        _say('Moving new repoview dir in place...', 1)
        shutil.rmtree(self.olddir)
        shutil.move(self.outdir, self.olddir)
        _say('done\n')

def usage(ecode=0):
    "Print usage and exit with ecode passed"
    sys.stderr.write("""
    repoview [-i name] [-x arch] [-k dir] [-l title] [-t] [-f] [-q] [repodir]
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
    -l title
        Describe the repository in a few words. By default, "RepoView" is used.
        E.g.:
        -l "Extras for Fedora Core 3 x86"
    -t
        Place the index.html into the top level of the repodir, instead of 
        just in repodata/index.html.
    -f
        Regenerate the pages even if the repomd checksum hasn't changed.
    -q
        Do not output anything except fatal erros.
    repodir
        Where to look for the 'repodata' directory.\n""" % DEFAULT_TEMPLATEDIR)
    sys.exit(ecode)

def main(args):
    "Main program code"
    global quiet #IGNORE:W0121
    if not args: 
        usage()
    ignore = []
    xarch = []
    toplevel = 0
    templatedir = DEFAULT_TEMPLATEDIR
    title = 'RepoView'
    force = 0
    try:
        gopts, cmds = getopt.getopt(args, 'i:x:k:l:tfqh', ['help'])
        if not cmds: 
            usage(1)
        for o, a in gopts:
            if o == '-i': 
                ignore.append(a)
            elif o == '-x': 
                xarch.append(a)
            elif o == '-k': 
                templatedir = a
            elif o == '-l': 
                title = a
            elif o == '-t': 
                toplevel = 1
            elif o == '-f': 
                force = 1
            elif o == '-q': 
                quiet = 1
            else: usage()
        repodir = cmds[0]
    except getopt.error, e:
        print "Error: %s" % e
        usage(1)
    if templatedir is None:
        templatedir = os.path.join(repodir, 'templates')
    rv = RepoView(repodir, ignore=ignore, xarch=xarch, force=force)
    rv.applyTemplates(templatedir, toplevel=toplevel, title=title)

if __name__ == '__main__':
    main(sys.argv[1:])
