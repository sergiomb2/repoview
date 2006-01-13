<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns:py="http://purl.org/kid/ns#">
<head>
  <title py:content="'RepoView: %s' % stats['title']"/>
  <link rel="stylesheet" href="${mkLinkUrl('layout/repostyle.css', isindex=1)}" type="text/css" />
  <link py:if="stats['dorss'] is not None"
	  rel="alternate" type="application/rss+xml" title="RSS" href="${mkLinkUrl('rss-feed', isrss=1, isindex=1)}" />
</head>
<body>
    <div class="levbar">
    <p class="pagetitle" py:content="stats['title']"/>
    <ul class="levbarlist">
      <li py:for="grp in groups.getSortedList()">
        <a class="nlink"
            href="${mkLinkUrl(grp, isindex=1)}"
            title="${grp.name}"
            py:content="len(grp.grid) > 20 and '%s...' % grp.grid[:17] or grp.grid"/>
      </li>
    </ul>
    </div>
    <div class="main">
        <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in letters.getSortedList()"
              class="nlink"
              href="${mkLinkUrl(letter, isindex=1)}" py:content="letter.grid"/>
          </span>]
        </p>
        <h2 py:content="stats['title']"/>
        <ul class="pkglist">
          <li>
            Indexed Packages: <span py:content="stats['pkgcount']"/>
          </li>
          <li>
            Available Architectures: 
            <span py:content="', '.join(stats['archlist'])"/>
          </li>
          <li py:if="stats['pkgignored']">
            Ignored Packages: <span py:content="stats['pkgignored']"/>
            (by name: 
            <span py:content="stats['ignorelist'] and ', '.join(stats['ignorelist']) or 'none'"/>;
            by arch:
            <span py:content="stats['ignorearchlist'] and ', '.join(stats['ignorearchlist']) or 'none'"/>)
          </li>
        </ul>
        <h3>Latest packages:</h3>
        <ul class="pkglist">
          <li py:for="pkg in groups['__latest__'].getSortedList(trim=0)">
            <em><span py:content="pkg.getTime('%d-%b-%Y')"/></em>:
            <a href="${mkLinkUrl(pkg, isindex=1)}" 
            	title="${pkg.summary}" class="inpage"
                py:content="'%s-%s-%s' % (pkg.n, pkg.v, pkg.r)"/>
          </li>
        </ul>
        <h3>Available Groups</h3>
        <ul class="pkglist">
          <li py:for="grp in groups.getSortedList()">
            <a href="${mkLinkUrl(grp, isindex=1)}" class="inpage"
                py:content="grp.name"/>
          </li>
        </ul>
        <p class="footernote">
          <span py:content="'Listing generated: %s by' % stats['gentime']"/>
          <a href="http://linux.duke.edu/projects/mini/repoview/"
            class="repoview" py:content="'RepoView-%s' % stats['VERSION']"/>
        </p>
    </div>
</body>
</html>
